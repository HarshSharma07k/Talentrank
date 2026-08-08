import os
import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer


def verify_phase2():
    try:
        # Load the index and jobs mapping
        index = faiss.read_index(os.path.join("data/processed", "jobs.faiss"))
        jobs_df = pd.read_parquet(os.path.join("data/processed", "jobs_clean.parquet"))
        model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        print(f"❌ Error loading assets: {e}")
        return

    print(f"✅ FAISS Index loaded. Total vectors: {index.ntotal}")

    # Dummy Resume Query
    dummy_resume = "Experienced software engineer specializing in Python, Machine Learning, and backend APIs."
    print(f"\nQuerying: '{dummy_resume}'\n")

    # Embed and normalize (Cosine Similarity requirement)
    query_emb = model.encode([dummy_resume], normalize_embeddings=True)

    # Search Top-5
    distances, indices = index.search(query_emb, k=5)

    print("Top 5 Retrieved Jobs (Bi-Encoder Only):")
    for i, idx in enumerate(indices[0]):
        # FAISS returns -1 if it can't find enough matches
        if idx == -1:
            continue

        # 1. Try treating idx as the actual job_id (Copilot's likely method)
        # We cast to string because your dataframe output says dtype='str'
        # Force both sides to string for a guaranteed match
        match = jobs_df[jobs_df["job_id"].astype(str) == str(idx)]

        if not match.empty:
            job_title = match.iloc[0]["job_title"]
        else:
            # 2. Fallback to row position just in case
            try:
                job_title = jobs_df.iloc[idx]["job_title"]
            except IndexError:
                job_title = f"Unknown Title (Raw FAISS ID: {idx})"

        print(f"{i + 1}. {job_title} (Score: {distances[0][i]:.4f})")


if __name__ == "__main__":
    verify_phase2()
