# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Literal

from google.adk import Agent, Context, Event, Workflow
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import RequestInput
from google.adk.events.event_actions import EventActions
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field


MODEL = "gemini-3.8-flash"
REVIEW_THRESHOLD = 100.0


class ExpenseReport(BaseModel):
    amount: float = Field(ge=0, description="Expense amount in USD")
    submitter: str
    category: str
    description: str
    date: str


class RiskAssessment(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    risk_factors: list[str]
    summary: str


def route_expense(node_input: ExpenseReport, ctx: Context) -> Event:
    ctx.state["expense_report"] = node_input.model_dump()
    route = "REVIEW" if node_input.amount >= REVIEW_THRESHOLD else "AUTO_APPROVE"
    return Event(actions=EventActions(route=route), output=node_input)


def auto_approve(node_input: ExpenseReport) -> Event:
    return Event(output={"status": "approved", **node_input.model_dump()})


review_agent = Agent(
    name="expense_risk_reviewer",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "Assess the expense report for financial or policy risk. Identify concrete "
        "risk factors and explain your judgment briefly. Do not approve or reject "
        "the expense and do not decide whether it should be routed; a human will "
        "make the approval decision."
    ),
    input_schema=ExpenseReport,
    output_schema=RiskAssessment,
    output_key="risk_assessment",
)


def request_human_approval(ctx: Context):
    yield RequestInput(
        message="Review the risk assessment, then approve or reject this expense.",
        payload={
            "expense_report": ctx.state["expense_report"],
            "risk_assessment": ctx.state["risk_assessment"],
        },
    )


def record_human_decision(node_input: dict, ctx: Context) -> Event:
    if node_input.get("decision") not in {"approve", "reject"}:
        raise ValueError("Human decision must be 'approve' or 'reject'.")
    return Event(
        output={
            "status": "approved" if node_input["decision"] == "approve" else "rejected",
            "expense_report": ctx.state["expense_report"],
            "risk_assessment": ctx.state["risk_assessment"],
        }
    )


root_agent = Workflow(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml.
    name="ambient_expense",
    input_schema=ExpenseReport,
    edges=[
        ("START", route_expense),
        (
            route_expense,
            {"AUTO_APPROVE": auto_approve, "REVIEW": review_agent},
        ),
        (review_agent, request_human_approval, record_human_decision),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
