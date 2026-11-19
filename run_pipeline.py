"""Run the whole project end to end: generate -> clean -> analyse."""
from src import analysis, clean, generate_data

if __name__ == "__main__":
    print("1/3 Generating raw data ...")
    generate_data.main()
    print("\n2/3 Cleaning and loading warehouse ...")
    clean.run()
    print("\n3/3 Running analysis ...")
    analysis.main()
    print("\nDone. Open reports/insights.md, or run:  streamlit run dashboard/app.py")
