import sys
import os

# 1. Tell Python to look in the main project directory for modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 2. Now the import will work perfectly
from src.talentrank.pipeline import match


def verify_phase3():
    dummy_resume = "Data Scientist with 4 years experience in Python, Pandas, SQL, and predictive modeling."
    print(f"Querying: '{dummy_resume}'\n")
    print("Running 2-Stage Pipeline (FAISS Retrieve -> Cross-Encoder Rerank)...")

    try:
        # Ask pipeline for top 5 (fetch top 50 from FAISS, rerank down to top 5)
        results = match(dummy_resume, top_k=50, top_n=5)
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        return

    print("✅ Pipeline executed successfully.\n")
    print("Final Top 5 Reranked Jobs:")
    for i, res in enumerate(results):
        # Handle variations in what Copilot might name the dictionary keys
        title = res.get("job_title") or res.get("title") or "Unknown Title"

        # Cross-encoder scores are usually logits (can be negative or > 1)
        score = res.get("cross_score") or res.get("score") or 0.0

        print(f"{i + 1}. [Score: {score:.4f}] {title}")

    print("\n🔍 Sanity Check: If these titles are Data Science roles, your entire AI pipeline is fully connected!")


if __name__ == "__main__":
    verify_phase3()
