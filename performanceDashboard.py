import streamlit as st
import pandas as pd
import plotly.express as px
from studentDatabase import StudentDatabase
class PerformanceDashboard:
    def __init__(self, database: StudentDatabase):
        self.database = database

    def render(self):
        st.header("📊 Performance Dashboard")
        if not self.database.has_data():
            st.info("No data found. Please go to 'Enter Data'.")
            return

        learner = st.selectbox("Select Learner", self.database.get_names())
        records = self.database.get_records_for(learner)
        subjects = [record["subject"] for record in records]
        subject = st.radio("Select Subject to View", subjects, horizontal=True)

        record = next(r for r in records if r["subject"] == subject)
        df = self._build_dataframe(record["scores"])
        self._show_chart(learner, subject, df)
        st.dataframe(df.T)

    @staticmethod
    def _build_dataframe(scores):
        return pd.DataFrame({
            "Exams": ["Exam 1", "Exam 2", "Exam 3"],
            "Scores": scores,
        })

    @staticmethod
    def _show_chart(name, subject, df):
        fig = px.bar(
            df,
            x="Exams",
            y="Scores",
            text="Scores",
            color="Exams",
            title=f"{subject} Performance: {name}",
        )
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig)
