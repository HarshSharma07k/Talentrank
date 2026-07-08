import pandas as pd
import os

def verify_phase1():
    # Adjusted paths to match your agent's exact output files
    processed_dir = "data/processed"
    
    jobs_file = os.path.join(processed_dir, "jobs_clean.parquet")
    resumes_file = os.path.join(processed_dir, "resumes_clean.parquet")
    eval_file = os.path.join(processed_dir, "relevance_eval.parquet")
    train_file = os.path.join(processed_dir, "relevance_train.parquet")

    # Sanity check file existence
    missing_files = [f for f in [jobs_file, resumes_file, eval_file] if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Error: Missing the following expected files: {missing_files}")
        print("Please check if they are located in a different directory (e.g., root or data/raw/).")
        return

    print("=== PHASE 1 VERIFICATION ===")
    
    # 1. Measure Corpus Size (Your <N> for the resume)
    jobs_df = pd.read_parquet(jobs_file)
    print(f"✅ Total Job Corpus Size: {len(jobs_df):,} postings")
    
    # 2. Measure Clean Resumes
    resumes_df = pd.read_parquet(resumes_file)
    print(f"✅ Total Clean Resumes: {len(resumes_df):,} profiles")

    # 3. Check Eval Split & Label Distribution
    eval_df = pd.read_parquet(eval_file)
    print(f"✅ Eval Split Size: {len(eval_df):,} pairs")
    
    if 'label' in eval_df.columns:
        positive_labels = eval_df['label'].sum()
        pct_positive = (positive_labels / len(eval_df)) * 100
        print(f"✅ Positive Relevance Labels (Eval): {positive_labels:,} ({pct_positive:.1f}%)")
    else:
        print("⚠️ Warning: 'label' column not found in evaluation file. Check your column names.")

    # 4. Optional Train Split Check
    if os.path.exists(train_file):
        train_df = pd.read_parquet(train_file)
        print(f"✅ Train Split Size: {len(train_df):,} pairs")

    # 5. Display Sample Row to inspect quality
    print("\n=== SAMPLE EVALUATION ROW ===")
    sample = eval_df.iloc[0]
    for col in eval_df.columns:
        # Truncate long text strings for clean terminal reading
        val = str(sample[col])
        if len(val) > 100:
            val = val[:97] + "..."
        print(f"{col}: {val}")

if __name__ == "__main__":
    verify_phase1()