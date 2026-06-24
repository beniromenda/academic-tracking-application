import streamlit as st 
from initial_implementation.studentDatabase import StudentDatabase
from initial_implementation.performanceDashboard import PerformanceDashboard
class AcademicTrackingApp:
    def __init__(self):
        st.set_page_config(page_title="School Performance Tracker")
        self.database = StudentDatabase()

    def run(self):
        st.sidebar.title("Navigation")
        page = st.sidebar.radio("Go to", ["Enter Data", "View Dashboard"])
        if page == "Enter Data":
            self._render_entry_page()
        else:
            PerformanceDashboard(self.database).render()

    def _render_entry_page(self):
        st.header("Enter School Based Assessment Scores")
        with st.form("data_form", clear_on_submit=True):
            name = st.text_input("Learner Name (e.g., Malcolm)")
            subject = st.selectbox("Subject", ["Maths", "English", "Science", "Swahili"])
            col1, col2, col3 = st.columns(3)
            with col1:
                e1 = st.number_input("Assessment 1", 0, 100)
            with col2:
                e2 = st.number_input("Assessment 2", 0, 100)
            with col3:
                e3 = st.number_input("Assessment 3", 0, 100)

            submit = st.form_submit_button("Save Details")
            if submit:
                if name:
                    self.database.add_record(name, subject, [e1, e2, e3])
                    st.success(f"Data for {name} in {subject} saved successfully!")
                else:
                    st.error("Please enter a learner name.")

if __name__ == "__main__":
    AcademicTrackingApp().run()