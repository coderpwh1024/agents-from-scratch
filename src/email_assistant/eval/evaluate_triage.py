"""在 LangSmith 上运行邮件分流评估并生成可视化结果。"""

from datetime import datetime
import os

import matplotlib.pyplot as plt
from langsmith import Client

from email_assistant.email_assistant import email_assistant
from email_assistant.eval.email_dataset import examples_triage


DATASET_NAME = "Interrupt Workshop: E-mail Triage Dataset"


def target_email_assistant(inputs: dict) -> dict:
    """通过工作流邮件助手处理一封邮件。"""
    try:
        response = email_assistant.invoke({"email_input": inputs["email_input"]})
        if "classification_decision" in response:
            return {"classification_decision": response["classification_decision"]}
        print("No classification_decision in response from workflow agent")
    except Exception as error:
        print(f"Error in workflow agent: {error}")
    return {"classification_decision": "unknown"}


def classification_evaluator(outputs: dict, reference_outputs: dict) -> bool:
    """检查邮件分类是否与参考答案完全一致。"""
    return outputs["classification_decision"].lower() == reference_outputs[
        "classification"
    ].lower()


def run_evaluation() -> str:
    """运行 LangSmith 评估并返回生成的图表路径。"""
    client = Client()
    if not client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="A dataset of e-mails and their triage decisions.",
        )
        client.create_examples(dataset_id=dataset.id, examples=examples_triage)

    experiment_results = client.evaluate(
        target_email_assistant,
        data=DATASET_NAME,
        evaluators=[classification_evaluator],
        experiment_prefix="E-mail assistant workflow",
        max_concurrency=2,
    )

    dataframe = experiment_results.to_pandas()
    feedback_key = "classification_evaluator"
    score_column = f"feedback.{feedback_key}"
    workflow_score = dataframe[score_column].mean() if score_column in dataframe else 0.0

    plt.figure(figsize=(10, 6))
    plt.bar(["Agentic Workflow"], [workflow_score], color="#5DA5DA", width=0.5)
    plt.xlabel("Agent Type")
    plt.ylabel("Average Score")
    plt.title("Email Triage Performance Comparison - Classification Score")
    plt.text(0, workflow_score + 0.02, f"{workflow_score:.2f}", ha="center", fontweight="bold")
    plt.ylim(0, 1.1)
    plt.grid(axis="y", linestyle="--", alpha=0.7)

    output_dir = "eval/results"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_path = f"{output_dir}/triage_comparison_{timestamp}.png"
    plt.savefig(plot_path)
    plt.close()

    print(f"Evaluation visualization saved to: {plot_path}")
    print(f"Agent With Router Score: {workflow_score:.2f}")
    return plot_path


if __name__ == "__main__":
    run_evaluation()
