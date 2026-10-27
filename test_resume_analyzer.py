
from pprint import pprint

from src.jobquest_ai.resume.resume_parser import parse_resume
from src.jobquest_ai.resume.resume_analyzer import (
    analyze_resume_to_dict,
    ResumeAnalysisError,
)


def main():
    try:
        # Step 1: Extract text from the uploaded resume.
        parsed_resume = parse_resume("sample_resume2.docx")

        # Step 2: Analyze the extracted text using the LLM.
        analysis = analyze_resume_to_dict(parsed_resume)

        # Step 3: Display the structured result.
        pprint(analysis, sort_dicts=False)

        # Step 4: Display a few fields for downstream use.
        print("\nCandidate summary:")
        print(analysis["candidate_summary"])

        print("\nSkills:")
        print(", ".join(analysis["skills"]))

        print("\nSuggested roles:")
        print(", ".join(analysis["suggested_roles"]))

    except ResumeAnalysisError as exc:
        print("Analysis error:", exc)
    except Exception as exc:
        print("Unexpected error:", exc)


if __name__ == "__main__":
    main()
