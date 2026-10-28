from pathlib import Path

from jobquest_ai.workflows.resume_workflow import run_resume_workflow


if __name__ == "__main__":
    resume_path = Path(__file__).with_name("sample_resume.pdf")
    result = run_resume_workflow(str(resume_path))
    print(result)