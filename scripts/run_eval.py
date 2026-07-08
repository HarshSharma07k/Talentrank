import pandas as pd
from sklearn.metrics import ndcg_score
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.talentrank.pipeline import retrieve_only, match

def evaluate_system():
    # Load the evaluation split
    try:
        eval_df = pd.read_parquet("data/processed/relevance_eval.parquet")
    except FileNotFoundError:
        print("❌ Error: Could not find relevance_eval.parquet. Are you in the project root?")
        return
        
    unique_resumes = eval_df['resume_text'].unique()[:50] # Evaluate on 50 resumes to save time
    
    baseline_ndcgs = []
    reranked_ndcgs = []

    print(f"Evaluating NDCG@10 on {len(unique_resumes)} held-out resumes...\n")

    for resume in unique_resumes:
        # Get true labels for this specific resume
        true_jobs = eval_df[eval_df['resume_text'] == resume]
        # Create a dictionary mapping job_id -> relevance label (1 or 0)
        true_labels_dict = dict(zip(true_jobs['job_id'].astype(str), true_jobs['relevance']))

        # --- 1. Baseline: Bi-encoder only ---
        baseline_results = retrieve_only(resume, top_k=10) 
        
        # Build label array and score array for NDCG
        baseline_true = [true_labels_dict.get(str(res.get('job_id')), 0) for res in baseline_results]
        
        # If Copilot didn't provide a 'score' key, we synthesize one based on rank order
        baseline_pred = [res.get('score', 10 - i) for i, res in enumerate(baseline_results)]
        
        # --- 2. Reranked: Bi-encoder + Cross-encoder ---
        reranked_results = match(resume, top_k=50, top_n=10)
        
        reranked_true = [true_labels_dict.get(str(res.get('job_id')), 0) for res in reranked_results]
        reranked_pred = [res.get('score', res.get('cross_score', 10 - i)) for i, res in enumerate(reranked_results)]

        # --- 3. Calculate NDCG@10 ---
        # Only score if there is at least 1 relevant job in the ground truth pool
        if sum(true_labels_dict.values()) > 0:
            if sum(baseline_true) > 0 or len(baseline_true) > 0:
                baseline_ndcgs.append(ndcg_score([baseline_true], [baseline_pred], k=10))
            if sum(reranked_true) > 0 or len(reranked_true) > 0:
                reranked_ndcgs.append(ndcg_score([reranked_true], [reranked_pred], k=10))

    final_baseline = np.mean(baseline_ndcgs) if baseline_ndcgs else 0
    final_reranked = np.mean(reranked_ndcgs) if reranked_ndcgs else 0

    print("=== FINAL METRICS (Put these on your resume!) ===")
    print(f"NDCG@10 (Bi-Encoder Baseline):  {final_baseline:.4f}")
    print(f"NDCG@10 (With Reranker):        {final_reranked:.4f}")
    print("=================================================")
    if final_reranked > final_baseline:
        print("✅ Success! The Cross-Encoder successfully improved your ranking precision.")

if __name__ == "__main__":
    evaluate_system()