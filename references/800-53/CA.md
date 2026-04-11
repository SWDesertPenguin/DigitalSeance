# NIST 800-53: CA — Assessment, Authorization, and Monitoring

## CA-1: Policy and Procedures
(ca-1_smt.a) Develop, document, and disseminate to {{ insert: param, ca-1_prm_1 }}:
    (ca-1_smt.a.1) {{ insert: param, ca-01_odp.03 }} assessment, authorization, and monitoring policy that:
      (ca-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ca-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and


**Guidance:** Assessment, authorization, and monitoring policy and procedures address the controls in the CA family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to securit

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- ca-1_obj.a
- ca-1_obj.b the {{ insert: param, ca-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the assessment, authorization, and monitoring policy and procedures;
- ca-1_obj.c

---

## CA-2: Control Assessments
(ca-2_smt.a) Select the appropriate assessor or assessment team for the type of assessment to be conducted;
  (ca-2_smt.b) Develop a control assessment plan that describes the scope of the assessment including:
    (ca-2_smt.b.1) Controls and control enhancements under assessment;
    (ca-2_smt.b.2) Assessment procedures to be used to determine control effectiveness; and
    (ca-2_smt.b.3) Assessment environment, assessment team, and assessment roles and responsibilities;
  (ca-2_smt.c) Ensure t

**Guidance:** Organizations ensure that control assessors possess the required skills and technical expertise to develop effective assessment plans and to conduct assessments of system-specific, hybrid, common, and program management controls, as appropriate. The required skills include general knowledge of risk

**Related:** AC-20, CA-5, CA-6, CA-7, PM-9, RA-5, RA-10, SA-11, SC-38, SI-3, SI-12, SR-2, SR-3

**Assessment Objectives:**
- ca-2_obj.a an appropriate assessor or assessment team is selected for the type of assessment to be conducted;
- ca-2_obj.b
- ca-2_obj.c the control assessment plan is reviewed and approved by the authorizing official or designated representative prior to conducting the assessment;
- ca-2_obj.d
- ca-2_obj.e a control assessment report is produced that documents the results of the assessment;
- ca-2_obj.f the results of the control assessment are provided to {{ insert: param, ca-02_odp.02 }}.

---

## CA-3: Information Exchange
(ca-3_smt.a) Approve and manage the exchange of information between the system and other systems using {{ insert: param, ca-03_odp.01 }};
  (ca-3_smt.b) Document, as part of each exchange agreement, the interface characteristics, security and privacy requirements, controls, and responsibilities for each system, and the impact level of the information communicated; and
  (ca-3_smt.c) Review and update the agreements {{ insert: param, ca-03_odp.03 }}.

**Guidance:** System information exchange requirements apply to information exchanges between two or more systems. System information exchanges include connections via leased lines or virtual private networks, connections to internet service providers, database sharing or exchanges of database transaction informa

**Related:** AC-4, AC-20, AU-16, CA-6, IA-3, IR-4, PL-2, PT-7, RA-3, SA-9, SC-7, SI-12

**Assessment Objectives:**
- ca-3_obj.a the exchange of information between the system and other systems is approved and managed using {{ insert: param, ca-03_odp.01 }};
- ca-3_obj.b
- ca-3_obj.c agreements are reviewed and updated {{ insert: param, ca-03_odp.03 }}.

---

## CA-5: Plan of Action and Milestones
(ca-5_smt.a) Develop a plan of action and milestones for the system to document the planned remediation actions of the organization to correct weaknesses or deficiencies noted during the assessment of the controls and to reduce or eliminate known vulnerabilities in the system; and
  (ca-5_smt.b) Update existing plan of action and milestones {{ insert: param, ca-05_odp }} based on the findings from control assessments, independent audits or reviews, and continuous monitoring activities.

**Guidance:** Plans of action and milestones are useful for any type of organization to track planned remedial actions. Plans of action and milestones are required in authorization packages and subject to federal reporting requirements established by OMB.

**Related:** CA-2, CA-7, PM-4, PM-9, RA-7, SI-2, SI-12

**Assessment Objectives:**
- ca-5_obj.a a plan of action and milestones for the system is developed to document the planned remediation actions of the organization to correct weaknesses or deficiencies noted during the assessment of the controls and to reduce or eliminate known vulnerabilities in the system;
- ca-5_obj.b existing plan of action and milestones are updated {{ insert: param, ca-05_odp }} based on the findings from control assessments, independent audits or reviews, and continuous monitoring activities.

---

## CA-6: Authorization
(ca-6_smt.a) Assign a senior official as the authorizing official for the system;
  (ca-6_smt.b) Assign a senior official as the authorizing official for common controls available for inheritance by organizational systems;
  (ca-6_smt.c) Ensure that the authorizing official for the system, before commencing operations:
    (ca-6_smt.c.1) Accepts the use of common controls inherited by the system; and
    (ca-6_smt.c.2) Authorizes the system to operate;
  (ca-6_smt.d) Ensure that the authorizing

**Guidance:** Authorizations are official management decisions by senior officials to authorize operation of systems, authorize the use of common controls for inheritance by organizational systems, and explicitly accept the risk to organizational operations and assets, individuals, other organizations, and the Na

**Related:** CA-2, CA-3, CA-7, PM-9, PM-10, RA-3, SA-10, SI-12

**Assessment Objectives:**
- ca-6_obj.a a senior official is assigned as the authorizing official for the system;
- ca-6_obj.b a senior official is assigned as the authorizing official for common controls available for inheritance by organizational systems;
- ca-6_obj.c
- ca-6_obj.d the authorizing official for common controls authorizes the use of those controls for inheritance by organizational systems;
- ca-6_obj.e the authorizations are updated {{ insert: param, ca-06_odp }}.

---

## CA-7: Continuous Monitoring
Develop a system-level continuous monitoring strategy and implement continuous monitoring in accordance with the organization-level continuous monitoring strategy that includes:
  (ca-7_smt.a) Establishing the following system-level metrics to be monitored: {{ insert: param, ca-07_odp.01 }};
  (ca-7_smt.b) Establishing {{ insert: param, ca-07_odp.02 }} for monitoring and {{ insert: param, ca-07_odp.03 }} for assessment of control effectiveness;
  (ca-7_smt.c) Ongoing control assessments in accor

**Guidance:** Continuous monitoring at the system level facilitates ongoing awareness of the system security and privacy posture to support organizational risk management decisions. The terms "continuous" and "ongoing" imply that organizations assess and monitor their controls and risks at a frequency sufficient

**Related:** AC-2, AC-6, AC-17, AT-4, AU-6, AU-13, CA-2, CA-5, CA-6, CM-3, CM-4, CM-6, CM-11, IA-5, IR-5, MA-2, MA-3, MA-4, PE-3, PE-6, PE-14, PE-16, PE-20, PL-2, PM-4, PM-6, PM-9, PM-10, PM-12, PM-14, PM-23, PM-28, PM-31, PS-7, PT-7, RA-3, RA-5, RA-7, RA-10, SA-8, SA-9, SA-11, SC-5, SC-7, SC-18, SC-38, SC-43, SI-3, SI-4, SI-12, SR-6

**Assessment Objectives:**
- ca-7_obj-1 a system-level continuous monitoring strategy is developed;
- ca-7_obj-2 system-level continuous monitoring is implemented in accordance with the organization-level continuous monitoring strategy;
- ca-7_obj.a system-level continuous monitoring includes establishment of the following system-level metrics to be monitored: {{ insert: param, ca-07_odp.01 }};
- ca-7_obj.b
- ca-7_obj.c system-level continuous monitoring includes ongoing control assessments in accordance with the continuous monitoring strategy;
- ca-7_obj.d system-level continuous monitoring includes ongoing monitoring of system and organization-defined metrics in accordance with the continuous monitoring strategy;
- ca-7_obj.e system-level continuous monitoring includes correlation and analysis of information generated by control assessments and monitoring;
- ca-7_obj.f system-level continuous monitoring includes response actions to address the results of the analysis of control assessment and monitoring information;
- ca-7_obj.g

---

## CA-8: Penetration Testing
Conduct penetration testing {{ insert: param, ca-08_odp.01 }} on {{ insert: param, ca-08_odp.02 }}.

**Guidance:** Penetration testing is a specialized type of assessment conducted on systems or individual system components to identify vulnerabilities that could be exploited by adversaries. Penetration testing goes beyond automated vulnerability scanning and is conducted by agents and teams with demonstrable ski

**Related:** RA-5, RA-10, SA-11, SR-5, SR-6

---

## CA-9: Internal System Connections
(ca-9_smt.a) Authorize internal connections of {{ insert: param, ca-09_odp.01 }} to the system;
  (ca-9_smt.b) Document, for each internal connection, the interface characteristics, security and privacy requirements, and the nature of the information communicated;
  (ca-9_smt.c) Terminate internal system connections after {{ insert: param, ca-09_odp.02 }} ; and
  (ca-9_smt.d) Review {{ insert: param, ca-09_odp.03 }} the continued need for each internal connection.

**Guidance:** Internal system connections are connections between organizational systems and separate constituent system components (i.e., connections between components that are part of the same system) including components used for system development. Intra-system connections include connections with mobile dev

**Related:** AC-3, AC-4, AC-18, AC-19, CM-2, IA-3, SC-7, SI-12

**Assessment Objectives:**
- ca-9_obj.a internal connections of {{ insert: param, ca-09_odp.01 }} to the system are authorized;
- ca-9_obj.b
- ca-9_obj.c internal system connections are terminated after {{ insert: param, ca-09_odp.02 }};
- ca-9_obj.d the continued need for each internal connection is reviewed {{ insert: param, ca-09_odp.03 }}.
