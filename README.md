# dashboard
dashbord for DT 
How to Run the SLA Incident Automation and Dashboard
This guide provides step-by-step instructions to set up and run the SLA Dashboard application.

1. Initial Setup
Before running the application, you need to set up your environment and install the required libraries.

A. Create a Project Folder:
First, create a dedicated folder on your computer for this project.

B. Save the Application File:
Save the Python code from the Canvas into a file named app.py inside your new project folder.

C. Install Required Libraries:
You will need Python 3.8 or newer. Open your terminal or command prompt and run the following command to install all the necessary libraries at once:

pip install streamlit pandas openpyxl fpdf2 plotly kaleido

streamlit: The main framework for the web app.

pandas & openpyxl: For reading and handling the data from your Excel file.

fpdf2: To generate the downloadable PDF reports.

plotly & kaleido: To create the interactive charts and save them as images for the PDF report.

2. Prepare Your Incident Data File
The application requires your incident data to be in a specific format.

A. File Type:
Your incident report must be an Excel file (.xlsx).

B. Sheet Name:
The Excel file must contain a sheet with the exact name Incidents - Raw Data  (note the space at the end).

C. Required Columns:
This sheet must contain the following columns. The names must match exactly.

Name: The name of the customer.

Duration: The downtime duration in seconds.

Datetime IST: The date and time of the incident.

Monitor ID: A unique identifier for each incident.

Owner: The name of the person or team assigned to the incident.

3. Running the Application
A. Open Your Terminal:
Navigate to your project folder using the terminal or command prompt.

B. Run the Command:
Execute the following command:

streamlit run app.py

Your default web browser will open with the application running.

4. Using the Application: A Step-by-Step Guide
Step 1: Upload Your Incident File
Use the "Upload Incident Report" button in the sidebar on the left to select and upload your prepared Excel file.

The application will load the data and the main interface will appear.

Step 2: Validate Incidents
In the sidebar, navigate to the "Incident Validation" page.

For each incident, you will see the Customer, Incident Owner (from your file), Duration, and Date.

Mark as: Choose whether the incident is a TP (True Positive) or FP (False Positive).

Validator Name: Enter your name as the person performing the validation.

Click "Submit Validation" to save your decision.

Use the "⬅️ Previous" and "Next ➡️" buttons to navigate between incidents.

Step 3: Analyze the SLA Dashboard
Navigate to the "SLA Dashboard" page.

At the top, you'll see key metrics for the selected timeframe.

Use the "Select Timeframe" filter in the sidebar to view data for "All Time", "Last 7 Days", etc. The charts and metrics will update automatically.

Step 4: Generate and Download Reports
Navigate to the "Reporting" page.

This page displays several charts summarizing the overall situation:

Customer Impact Ratio: Shows the proportion of customers with and without downtime.

TP vs. FP Ratio: Visualizes the accuracy of your alerts.

Incident Ownership: Shows how many incidents are assigned to each owner from your Excel file.

Validation Workload: Shows how many incidents were validated by each person using the tool.

Click the "⬇️ Download CSV Report" or "📄 Download PDF Report" buttons to get a copy of the data. The PDF report will include all the charts from this page.
