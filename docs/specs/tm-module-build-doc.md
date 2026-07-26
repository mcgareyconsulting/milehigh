# The Brain: Time & Materials (T&M) Module — Build Document

## 1. Module Overview
The Time & Materials (T&M) Module is a high-priority, standalone feature set designed to replace the current single-page paper T&M form. It lives inside The Brain and provides a fully digital, mobile-friendly workflow for capturing field work, obtaining on-site signatures, and generating Change Order (CO) requests.

## 2. Core Workflow

1. **Creation & Auto-Population:** A foreman or subcontractor opens a new T&M ticket on their mobile device. The system automatically populates the job number, project name, GC contact, contract terms, and the foreman's name from the project hub.
2. **Data Entry:** The user logs the date, location, crew members, hours worked, equipment used, and selects materials from a searchable drop-down database. Photos and videos of the work are attached directly from the device.
3. **On-Site Signature:** The GC's on-site representative reviews the ticket on the mobile device, signs using a finger or digital pen in the signature box, and types their printed name.
4. **Internal Approval:** The completed ticket routes to the Project Manager (PM) and Field Superintendent for internal review and approval.
5. **Change Order Generation:** Upon internal approval, the system generates a formal Change Order Request PDF. This document clearly breaks down hours, materials, and separately details Overhead & Profit (O&P) percentages pulled directly from the contract review.
6. **Distribution:** BB01 automatically emails the CO Request PDF to the GC, copying the PM, Foreman, and Billing team.
7. **Follow-Up:** BB01 monitors the CO Log and automatically sends a follow-up email to the GC if the CO remains unapproved after 14 days.
8. **Invoicing:** Once the GC approves the CO, the approved PDF is uploaded, and the value is added to the Schedule of Values (SOV) for monthly invoicing.

## 3. Data Structure & Fields

### Ticket Header (Auto-Populated)
*   Project Code (3-Digit)
*   Project Name
*   GC Company & Contact Name
*   MHMW Foreman Name
*   Contract O&P Values (Hidden from Subcontractors)

### Work Details (User Input)
*   Date of Work
*   Location / Area of Work
*   Detailed Description of Work Performed

### Labor & Materials (User Input)
*   **Labor:** Worker Name, Trade Classification, Hours Worked.
*   **Materials:** Searchable drop-down of standard MHMW materials. User inputs quantity and length. Background logic applies pricing (hidden from Subcontractors).
*   **Equipment:** List of equipment used and hours.

### Media & Signatures
*   **Attachments:** Photo and video uploads.
*   **Signature Block:** Digital drawing canvas for signature, plus a text field for the printed name.

## 4. Permission Tiers

| User Role | Access Level |
| :--- | :--- |
| **Subcontractor** | Can input labor hours, select materials (no pricing visible), add equipment, attach photos, and collect signatures. Cannot view financial data, labor rates, or O&P. |
| **Field Crew / Foreman** | Same as Subcontractor, plus the ability to view completed tickets for their assigned project. |
| **PM / Field Superintendent** | Full access to ticket data, including realized costs, labor rates, and O&P. Can approve tickets internally. |
| **Global Admin** | Full system access across all projects and financial data. |

## 5. Development Priorities for this Module

1. **Mobile-First Interface:** The ticket creation and signature collection must be flawless on mobile devices (phones and iPads) used in the field.
2. **O&P Separation:** The generated CO Request PDF must explicitly separate the base costs from the Overhead & Profit, ensuring clear transparency for the GC and owners.
3. **Contract Integration:** The system must seamlessly pull the specific O&P values established during the contract review phase for that project.
4. **Automated Follow-Up:** Implement the 14-day BB01 follow-up trigger for unapproved COs.
