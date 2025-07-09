import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from fpdf import FPDF
import io
import os

# --- Configuration ---
DB_FILE_PATH = "incidents.db"
RAW_DATA_SHEET_NAME = 'Incidents - Raw Data '  # Note the trailing space as in the original script

# --- Page Configuration (Must be the first Streamlit command) ---
st.set_page_config(
    page_title="SLA Incident Dashboard",
    page_icon="📊",
    layout="wide"
)


# --- Database Setup ---
@st.cache_resource
def get_db_connection():
    """Establishes and returns a cached database connection."""
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    # Use row_factory to access columns by name
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the database table if it doesn't exist."""
    conn = get_db_connection()
    c = conn.cursor()
    # The 'reviewer' column will now store the 'validator's' name.
    c.execute('''
        CREATE TABLE IF NOT EXISTS validations (
            id INTEGER PRIMARY KEY,
            monitor_id TEXT UNIQUE,
            decision TEXT,
            reviewer TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()


# --- Data Loading ---
@st.cache_data
def load_incident_data(uploaded_file):
    """Loads and caches the raw incident data."""
    try:
        df = pd.read_excel(uploaded_file, sheet_name=RAW_DATA_SHEET_NAME)
        # Standardize datetime column, handling different formats
        if 'Datetime IST' in df.columns:
            df['Datetime IST'] = pd.to_datetime(df['Datetime IST'], format='mixed', dayfirst=True)

        # Ensure Monitor ID is a string and stripped of whitespace for consistency
        if 'Monitor ID' in df.columns:
            df['Monitor ID'] = df['Monitor ID'].astype(str).str.strip()

        # Ensure Owner is a string and stripped of whitespace
        if 'Owner' in df.columns:
            df['Owner'] = df['Owner'].astype(str).str.strip()

        # Ensure required columns exist, now including 'Owner'
        required_cols = ['Name', 'Duration', 'Datetime IST', 'Monitor ID', 'Owner']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Excel file must contain the following columns: {', '.join(required_cols)}")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"An error occurred while reading the Excel file: {e}")
        return None


@st.cache_data
def get_all_validations():
    """Fetches all existing validations from the database."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT monitor_id, decision, reviewer FROM validations")
    # 'reviewer' column holds the name of the person who validated the incident
    return {str(row['monitor_id']).strip(): {'decision': row['decision'], 'reviewer': row['reviewer']} for row in
            c.fetchall()}


# --- Core Logic ---
def compute_sla_metrics(tp_incidents_df, all_incidents_df):
    """
    Computes SLA metrics from True Positive incidents and a full list of customers.
    """
    if tp_incidents_df.empty:
        summary = pd.DataFrame(columns=['Customer', 'Total Downtime (sec)', 'Avg Downtime (sec)', 'Min Downtime (sec)',
                                        'Max Downtime (sec)'])
    else:
        summary = tp_incidents_df.groupby('Name')['Duration'].agg(['sum', 'mean', 'min', 'max']).reset_index()
        summary.columns = ['Customer', 'Total Downtime (sec)', 'Avg Downtime (sec)', 'Min Downtime (sec)',
                           'Max Downtime (sec)']
        summary['Avg Downtime (sec)'] = summary['Avg Downtime (sec)'].round(2)

    # Correctly identify customers with no downtime for the given period
    all_customers = set(all_incidents_df['Name'].unique())
    downtime_customers = set(summary['Customer'])
    no_downtime_customers = all_customers - downtime_customers

    return summary, no_downtime_customers


# --- Report Generation ---
def generate_pdf_report(summary_df, no_downtime_customers, validations, validated_tp_df):
    """Generates a PDF report with charts and tables, then returns it as bytes."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', size=16)
    pdf.cell(0, 10, txt="SLA Incident Report", ln=True, align='C')

    # --- Add Charts to PDF ---
    # This functionality requires the 'kaleido' library: pip install kaleido
    try:
        import plotly.express as px

        # Chart 1: Customer Impact Ratio
        num_no_downtime = len(no_downtime_customers)
        num_tp_downtime = validated_tp_df['Name'].nunique()
        if num_no_downtime > 0 or num_tp_downtime > 0:
            pdf.ln(10)
            pdf.set_font("Arial", 'B', size=12)
            pdf.cell(0, 10, "Customer Impact Ratio", ln=True)
            impact_data = pd.DataFrame({
                'Category': ['Customers with No Downtime', 'Customers with TP Downtime'],
                'Count': [num_no_downtime, num_tp_downtime]
            })
            fig_impact = px.pie(impact_data, values='Count', names='Category',
                                color_discrete_map={'Customers with No Downtime': 'green',
                                                    'Customers with TP Downtime': 'red'},
                                template='plotly_white')
            impact_path = "temp_impact_chart.png"
            fig_impact.write_image(impact_path, width=600, height=400)
            pdf.image(impact_path, w=170)
            os.remove(impact_path)

        # Chart 2: TP vs FP Ratio
        total_tp = len([val for val in validations.values() if val['decision'] == 'TP'])
        total_fp = len([val for val in validations.values() if val['decision'] == 'FP'])
        if total_tp > 0 or total_fp > 0:
            pdf.ln(5)
            pdf.set_font("Arial", 'B', size=12)
            pdf.cell(0, 10, "TP vs. FP Ratio", ln=True)
            pie_data = pd.DataFrame({'Decision': ['True Positives', 'False Positives'], 'Count': [total_tp, total_fp]})
            fig_pie = px.pie(pie_data, values='Count', names='Decision',
                             color_discrete_map={'True Positives': 'red', 'False Positives': 'green'},
                             template='plotly_white')
            pie_path = "temp_pie_chart.png"
            fig_pie.write_image(pie_path, width=600, height=400)
            pdf.image(pie_path, w=170)
            os.remove(pie_path)

        # Chart 3: Incident Ownership
        if not validated_tp_df.empty:
            pdf.add_page()  # Add a new page for more charts
            pdf.ln(5)
            pdf.set_font("Arial", 'B', size=12)
            pdf.cell(0, 10, "Incident Ownership (True Positives)", ln=True)
            owner_counts = validated_tp_df['Owner'].value_counts().reset_index()
            owner_counts.columns = ['Owner', 'Incidents Owned']
            fig_owner = px.bar(owner_counts, x='Owner', y='Incidents Owned', text_auto=True,
                               color_discrete_sequence=px.colors.qualitative.Pastel,
                               template='plotly_white')
            owner_path = "temp_owner_chart.png"
            fig_owner.write_image(owner_path, width=800, height=400)
            pdf.image(owner_path, w=170)
            os.remove(owner_path)

        # Chart 4: Validator Workload
        tp_validators = [val['reviewer'] for val in validations.values() if val['decision'] == 'TP']
        if tp_validators:
            pdf.ln(5)
            pdf.set_font("Arial", 'B', size=12)
            pdf.cell(0, 10, "Validation Workload", ln=True)
            validator_counts = pd.Series(tp_validators).value_counts().reset_index()
            validator_counts.columns = ['Validator', 'Incidents Validated']
            fig_validator = px.bar(validator_counts, x='Validator', y='Incidents Validated', text_auto=True,
                                   color_discrete_sequence=px.colors.qualitative.Vivid,
                                   template='plotly_white')
            validator_path = "temp_validator_chart.png"
            fig_validator.write_image(validator_path, width=800, height=400)
            pdf.image(validator_path, w=170)
            os.remove(validator_path)

    except ImportError:
        pdf.ln(10)
        pdf.set_font("Arial", 'I', size=10)
        pdf.cell(0, 10, txt="(Chart generation failed. Please ensure 'plotly' and 'kaleido' are installed.)", ln=True)
    except Exception as e:
        pdf.ln(10)
        pdf.set_font("Arial", 'I', size=10)
        pdf.cell(0, 10, txt=f"(An error occurred during chart generation: {e})", ln=True)

    # --- Add Tables to PDF ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', size=16)
    pdf.cell(0, 10, "Detailed Report Data", ln=True, align='C')
    pdf.ln(10)

    # Downtime Summary Table
    if not summary_df.empty:
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 10, "Downtime Summary by Customer", ln=True)
        pdf.set_font("Arial", 'B', size=10)
        col_widths = {'Customer': 70, 'Total Downtime (sec)': 40, 'Avg Downtime (sec)': 40, 'Min Downtime (sec)': 20,
                      'Max Downtime (sec)': 20}
        for col_name in summary_df.columns:
            pdf.cell(col_widths.get(col_name, 40), 10, txt=col_name, border=1, align='C')
        pdf.ln()
        pdf.set_font("Arial", size=10)
        for _, row in summary_df.iterrows():
            for col_name in summary_df.columns:
                pdf.cell(col_widths.get(col_name, 40), 10, txt=str(row[col_name]), border=1)
            pdf.ln()
    else:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No downtime incidents recorded for this period.", ln=True)

    pdf.ln(10)

    # No Downtime Section
    pdf.set_font("Arial", 'B', size=12)
    pdf.cell(0, 10, "Customers with No Downtime Incidents", ln=True)
    pdf.set_font("Arial", size=10)
    if no_downtime_customers:
        pdf.multi_cell(0, 5, txt=', '.join(sorted(list(no_downtime_customers))))
    else:
        pdf.cell(0, 10, "All customers experienced at least one downtime incident.", ln=True)

    return pdf.output(dest='S').encode('latin-1')


# --- Streamlit Pages ---
def page_validator(incident_data, validations):
    """UI for the Incident Validation page."""
    st.header("Incident Validation")
    st.write("Review each incident, mark it as TP/FP, and record your name as the validator.")

    if 'current_incident_idx' not in st.session_state:
        st.session_state.current_incident_idx = 0

    total_incidents = len(incident_data)
    if total_incidents == 0:
        st.warning("No incidents to validate.")
        return

    idx = st.session_state.current_incident_idx
    row = incident_data.iloc[idx]
    monitor_id = str(row['Monitor ID']).strip()

    st.progress((idx + 1) / total_incidents)

    with st.container(border=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Customer", row['Name'])
        col2.metric("Incident Owner", row['Owner'])
        col3.metric("Duration (sec)", row['Duration'])
        col4.metric("Date", row['Datetime IST'].strftime('%Y-%m-%d %H:%M'))

        existing_decision = validations.get(monitor_id, {}).get('decision', 'Unmarked')
        decision_index = ['Unmarked', 'TP', 'FP'].index(existing_decision)

        decision = st.radio(
            "Mark as:",
            ('Unmarked', 'TP', 'FP'),
            index=decision_index,
            key=f"decision_{monitor_id}",
            horizontal=True
        )

        validator_name = st.text_input(
            "Validator Name",
            value=validations.get(monitor_id, {}).get('reviewer', st.session_state.get('validator_name', '')),
            key=f"validator_{monitor_id}"
        )

        if st.button("Submit Validation", key=f"submit_{monitor_id}", type="primary"):
            if decision != 'Unmarked' and validator_name:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO validations (monitor_id, decision, reviewer, timestamp)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(monitor_id) DO UPDATE SET
                    decision=excluded.decision,
                    reviewer=excluded.reviewer,
                    timestamp=excluded.timestamp
                """, (monitor_id, decision, validator_name, datetime.now().isoformat()))
                conn.commit()
                st.success(f"Validation for {monitor_id} saved.")
                st.session_state.validator_name = validator_name
                get_all_validations.clear()
            else:
                st.warning("Please select a decision (TP/FP) and enter a validator name.")

    col_nav1, _, col_nav3 = st.columns([1, 2, 1])
    if col_nav1.button("⬅️ Previous", use_container_width=True, disabled=(idx == 0)):
        st.session_state.current_incident_idx -= 1
        st.rerun()
    if col_nav3.button("Next ➡️", use_container_width=True, disabled=(idx >= total_incidents - 1)):
        st.session_state.current_incident_idx += 1
        st.rerun()


def page_dashboard(all_incidents_df, validated_tp_df):
    """UI for the SLA Dashboard page."""
    st.header("SLA Dashboard")

    st.sidebar.header("Filters")
    timeframe = st.sidebar.selectbox(
        "Select Timeframe",
        ["All Time", "Last 7 Days", "Last 30 Days", "Last 90 Days"],
        key="dashboard_timeframe"
    )

    filtered_df = validated_tp_df.copy()
    if timeframe != "All Time":
        days = int(timeframe.split(" ")[1])
        start_date = pd.Timestamp.now(tz='UTC').floor('D') - pd.DateOffset(days=days)
        filtered_df['Datetime IST'] = pd.to_datetime(filtered_df['Datetime IST'])
        if filtered_df['Datetime IST'].dt.tz is None:
            filtered_df['Datetime IST'] = filtered_df['Datetime IST'].dt.tz_localize('UTC')
        filtered_df = filtered_df[filtered_df['Datetime IST'] >= start_date]

    summary_df, no_downtime_customers_for_period = compute_sla_metrics(filtered_df, all_incidents_df)

    total_downtime = summary_df['Total Downtime (sec)'].sum()
    avg_downtime = summary_df['Avg Downtime (sec)'].mean()
    num_incidents = len(filtered_df)
    num_customers_affected = summary_df['Customer'].nunique()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Incidents (TP)", f"{num_incidents:,.0f}")
    kpi2.metric("Total Downtime (sec)", f"{total_downtime:,.0f}")
    kpi3.metric("Avg. Downtime (sec)", f"{avg_downtime:,.2f}" if not pd.isna(avg_downtime) else "0")
    kpi4.metric("Customers Affected", f"{num_customers_affected:,.0f}")

    st.divider()

    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("Total Downtime per Customer")
        if not summary_df.empty:
            import plotly.express as px

            # Define color based on downtime
            def get_color(seconds):
                if seconds > 900:  # More than 15 minutes
                    return 'red'
                elif seconds > 600:  # More than 10 minutes
                    return 'orange'
                else:  # 10 minutes or less
                    return 'lightskyblue'

            summary_df['Color'] = summary_df['Total Downtime (sec)'].apply(get_color)

            fig = px.bar(
                summary_df.sort_values('Total Downtime (sec)', ascending=False),
                x='Customer',
                y='Total Downtime (sec)',
                title='Total Downtime per Customer (sec)',
                color='Color',  # Use the new Color column
                color_discrete_map='identity'  # Tell plotly to use the color names directly
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No True Positive incidents in the selected timeframe.")

    with col2:
        st.subheader("SLA Summary Table")

        # Define styling function for the summary table
        def style_downtime_table(row):
            style = ''
            seconds = row['Total Downtime (sec)']
            if seconds > 900:  # More than 15 minutes
                style = 'background-color: #ffcccc'  # Light Red
            elif seconds > 600:  # More than 10 minutes
                style = 'background-color: #ffe5cc'  # Light Orange
            else:  # 10 minutes or less
                style = 'background-color: #cceeff'  # Light Blue
            return [style] * len(row)

        if not summary_df.empty:
            # Apply the style to the DataFrame for display
            st.dataframe(summary_df.drop(columns=['Color']).style.apply(style_downtime_table, axis=1),
                         use_container_width=True)
        else:
            # Display an empty dataframe if there's no data
            st.dataframe(summary_df, use_container_width=True)

        st.subheader(f"Customers with No Downtime ({timeframe})")
        if no_downtime_customers_for_period:
            st.dataframe(pd.DataFrame(sorted(list(no_downtime_customers_for_period)), columns=["Customer"]),
                         use_container_width=True)
        else:
            st.info("All customers had at least one downtime incident in this period.")


def page_reporting(summary_df, no_downtime_customers, validations, validated_tp_df):
    """UI for the Reporting page."""
    st.header("Generate Reports")
    st.write("This page provides a summary of all validated incidents and allows you to download reports.")

    # --- Managerial Summary Section ---
    st.subheader("High-Level Impact Summary")

    total_tp = len([val for val in validations.values() if val['decision'] == 'TP'])
    total_fp = len([val for val in validations.values() if val['decision'] == 'FP'])
    avg_downtime = validated_tp_df['Duration'].mean() if not validated_tp_df.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total True Positives (TP)", f"{total_tp:,}")
    col2.metric("Total False Positives (FP)", f"{total_fp:,}")
    col3.metric("Average Downtime per TP (sec)", f"{avg_downtime:,.2f}")

    st.divider()

    # --- Customer Impact Ratio Chart ---
    st.subheader("Customer Impact Ratio")
    num_no_downtime = len(no_downtime_customers)
    num_tp_downtime = validated_tp_df['Name'].nunique()

    if num_no_downtime > 0 or num_tp_downtime > 0:
        import plotly.express as px
        impact_data = pd.DataFrame({
            'Category': ['Customers with No Downtime', 'Customers with TP Downtime'],
            'Count': [num_no_downtime, num_tp_downtime]
        })
        fig_impact = px.pie(impact_data, values='Count', names='Category', title='Customer Downtime Impact Ratio',
                            color_discrete_map={'Customers with No Downtime': 'green',
                                                'Customers with TP Downtime': 'red'})
        st.plotly_chart(fig_impact, use_container_width=True)
    else:
        st.info("No data available to display customer impact ratio.")

    st.divider()

    # --- TP vs FP Ratio Chart ---
    st.subheader("TP vs. FP Ratio")
    if total_tp > 0 or total_fp > 0:
        import plotly.express as px
        pie_data = pd.DataFrame({
            'Decision': ['True Positives', 'False Positives'],
            'Count': [total_tp, total_fp]
        })
        fig_pie = px.pie(pie_data, values='Count', names='Decision', title='TP vs. FP Ratio',
                         color_discrete_map={'True Positives': 'red', 'False Positives': 'green'})
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No validation data available to display a chart. Please validate incidents first.")

    st.divider()

    # --- Incident Ownership Chart (from Excel) ---
    st.subheader("Incident Ownership")
    if not validated_tp_df.empty:
        owner_counts = validated_tp_df['Owner'].value_counts().reset_index()
        owner_counts.columns = ['Owner', 'Incidents Owned']

        import plotly.express as px
        fig_owner = px.bar(
            owner_counts,
            x='Owner',
            y='Incidents Owned',
            title='True Positive Incidents per Owner',
            text_auto=True,
            color='Owner'
        )
        fig_owner.update_layout(showlegend=False)
        st.plotly_chart(fig_owner, use_container_width=True)
    else:
        st.info("No True Positive incidents to analyze for ownership.")

    st.divider()

    # --- Validator Workload Chart ---
    st.subheader("Validation Workload")
    tp_validators = [
        val['reviewer'] for val in validations.values() if val['decision'] == 'TP'
    ]
    if tp_validators:
        validator_counts = pd.Series(tp_validators).value_counts().reset_index()
        validator_counts.columns = ['Validator', 'Incidents Validated']

        import plotly.express as px
        fig_validator = px.bar(
            validator_counts,
            x='Validator',
            y='Incidents Validated',
            title='Incidents Validated per Person',
            text_auto=True,
            color='Validator'
        )
        fig_validator.update_layout(showlegend=False)
        st.plotly_chart(fig_validator, use_container_width=True)
    else:
        st.info("No True Positive incidents have been validated yet.")

    st.divider()

    # --- Download Section ---
    st.subheader("Download Full Reports")
    if not summary_df.empty or no_downtime_customers:
        col1, col2 = st.columns(2)
        with col1:
            csv_buffer = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Download CSV Report",
                data=csv_buffer,
                file_name=f"sla_summary_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col2:
            pdf_bytes = generate_pdf_report(summary_df, no_downtime_customers, validations, validated_tp_df)
            st.download_button(
                label="📄 Download PDF Report",
                data=pdf_bytes,
                file_name=f"sla_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    else:
        st.warning("No data available to generate a report. Please validate incidents first.")

    st.divider()

    # --- Report Preview Section ---
    st.subheader("Report Data Preview")
    st.dataframe(summary_df)
    st.subheader("Customers with No Downtime (All Time)")
    st.write(", ".join(sorted(list(no_downtime_customers))))


# --- Main App Logic ---
def main():
    """Main function to run the Streamlit app."""
    st.title("📊 SLA Incident Automation and Dashboard")

    init_db()

    st.sidebar.title("Setup")
    uploaded_file = st.sidebar.file_uploader("Upload Incident Report", type=['xlsx'])

    # --- Debugging Tool ---
    st.sidebar.divider()
    if st.sidebar.button("Clear All Validations"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM validations")
        conn.commit()
        get_all_validations.clear()
        st.sidebar.success("All validations have been cleared.")
        st.rerun()

    if uploaded_file is None:
        st.info("Please upload your incident report Excel file to begin.")
        st.stop()

    all_incidents_df = load_incident_data(uploaded_file)

    if all_incidents_df is None or all_incidents_df.empty:
        st.error("The uploaded file could not be processed. Please check the file format and column names.")
        st.stop()

    validations = get_all_validations()

    tp_monitor_ids = [mid for mid, val in validations.items() if val['decision'] == 'TP']
    validated_tp_df = all_incidents_df[all_incidents_df['Monitor ID'].isin(tp_monitor_ids)]

    # Calculate global SLA metrics for the reporting page (always "All Time")
    summary_df, no_downtime_customers = compute_sla_metrics(validated_tp_df, all_incidents_df)

    pages = {
        "SLA Dashboard": page_dashboard,
        "Incident Validation": page_validator,
        "Reporting": page_reporting,
    }

    st.sidebar.title("Navigation")
    selection = st.sidebar.radio("Go to", list(pages.keys()), key="page_selection")

    page = pages[selection]

    if selection == "Incident Validation":
        page(all_incidents_df, validations)
    elif selection == "SLA Dashboard":
        page(all_incidents_df, validated_tp_df)
    elif selection == "Reporting":
        page(summary_df, no_downtime_customers, validations, validated_tp_df)


if __name__ == "__main__":
    main()
