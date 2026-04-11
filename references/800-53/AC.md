# NIST 800-53: AC — Access Control

## AC-1: Policy and Procedures
(ac-1_smt.a) Develop, document, and disseminate to {{ insert: param, ac-1_prm_1 }}:
    (ac-1_smt.a.1) {{ insert: param, ac-01_odp.03 }} access control policy that:
      (ac-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ac-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (ac-1_smt.a.2) Procedures t

**Guidance:** Access control policy and procedures address the controls in the AC family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance. Th

**Related:** IA-1, PM-9, PM-24, PS-8, SI-12

**Assessment Objectives:**
- ac-1_obj.a
- ac-1_obj.b the {{ insert: param, ac-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the access control policy and procedures;
- ac-1_obj.c

---

## AC-2: Account Management
(ac-2_smt.a) Define and document the types of accounts allowed and specifically prohibited for use within the system;
  (ac-2_smt.b) Assign account managers;
  (ac-2_smt.c) Require {{ insert: param, ac-02_odp.01 }} for group and role membership;
  (ac-2_smt.d) Specify:
    (ac-2_smt.d.1) Authorized users of the system;
    (ac-2_smt.d.2) Group and role membership; and
    (ac-2_smt.d.3) Access authorizations (i.e., privileges) and {{ insert: param, ac-02_odp.02 }} for each account;
  (ac-2_smt.e

**Guidance:** Examples of system account types include individual, shared, group, system, guest, anonymous, emergency, developer, temporary, and service. Identification of authorized system users and the specification of access privileges reflect the requirements in other controls in the security plan. Users requ

**Related:** AC-3, AC-5, AC-6, AC-17, AC-18, AC-20, AC-24, AU-2, AU-12, CM-5, IA-2, IA-4, IA-5, IA-8, MA-3, MA-5, PE-2, PL-4, PS-2, PS-4, PS-5, PS-7, PT-2, PT-3, SC-7, SC-12, SC-13, SC-37

**Assessment Objectives:**
- ac-2_obj.a
- ac-2_obj.b account managers are assigned;
- ac-2_obj.c {{ insert: param, ac-02_odp.01 }} for group and role membership are required;
- ac-2_obj.d
- ac-2_obj.e approvals are required by {{ insert: param, ac-02_odp.03 }} for requests to create accounts;
- ac-2_obj.f
- ac-2_obj.g the use of accounts is monitored;
- ac-2_obj.h
- ac-2_obj.i
- ac-2_obj.j accounts are reviewed for compliance with account management requirements {{ insert: param, ac-02_odp.10 }};
- ... and 2 more

---

## AC-3: Access Enforcement
Enforce approved authorizations for logical access to information and system resources in accordance with applicable access control policies.

**Guidance:** Access control policies control access between active entities or subjects (i.e., users or processes acting on behalf of users) and passive entities or objects (i.e., devices, files, records, domains) in organizational systems. In addition to enforcing authorized access at the system level and recog

**Related:** AC-2, AC-4, AC-5, AC-6, AC-16, AC-17, AC-18, AC-19, AC-20, AC-21, AC-22, AC-24, AC-25, AT-2, AT-3, AU-9, CA-9, CM-5, CM-11, IA-2, IA-5, IA-6, IA-7, IA-11, IA-13, MA-3, MA-4, MA-5, MP-4, PM-2, PS-3, PT-2, PT-3, SA-17, SC-2, SC-3, SC-4, SC-12, SC-13, SC-28, SC-31, SC-34, SI-4, SI-8

---

## AC-4: Information Flow Enforcement
Enforce approved authorizations for controlling the flow of information within the system and between connected systems based on {{ insert: param, ac-04_odp }}.

**Guidance:** Information flow control regulates where information can travel within a system and between systems (in contrast to who is allowed to access the information) and without regard to subsequent accesses to that information. Flow control restrictions include blocking external traffic that claims to be f

**Related:** AC-3, AC-6, AC-16, AC-17, AC-19, AC-21, AU-10, CA-3, CA-9, CM-7, PL-9, PM-24, SA-17, SC-4, SC-7, SC-16, SC-31

---

## AC-5: Separation of Duties
(ac-5_smt.a) Identify and document {{ insert: param, ac-05_odp }} ; and
  (ac-5_smt.b) Define system access authorizations to support separation of duties.

**Guidance:** Separation of duties addresses the potential for abuse of authorized privileges and helps to reduce the risk of malevolent activity without collusion. Separation of duties includes dividing mission or business functions and support functions among different individuals or roles, conducting system su

**Related:** AC-2, AC-3, AC-6, AU-9, CM-5, CM-11, CP-9, IA-2, IA-4, IA-5, IA-12, MA-3, MA-5, PS-2, SA-8, SA-17

**Assessment Objectives:**
- ac-5_obj.a {{ insert: param, ac-05_odp }} are identified and documented;
- ac-5_obj.b system access authorizations to support separation of duties are defined.

---

## AC-6: Least Privilege
Employ the principle of least privilege, allowing only authorized accesses for users (or processes acting on behalf of users) that are necessary to accomplish assigned organizational tasks.

**Guidance:** Organizations employ least privilege for specific duties and systems. The principle of least privilege is also applied to system processes, ensuring that the processes have access to systems and operate at privilege levels no higher than necessary to accomplish organizational missions or business fu

**Related:** AC-2, AC-3, AC-5, AC-16, CM-5, CM-11, PL-2, PM-12, SA-8, SA-15, SA-17, SC-38

---

## AC-7: Unsuccessful Logon Attempts
(ac-7_smt.a) Enforce a limit of {{ insert: param, ac-07_odp.01 }} consecutive invalid logon attempts by a user during a {{ insert: param, ac-07_odp.02 }} ; and
  (ac-7_smt.b) Automatically {{ insert: param, ac-07_odp.03 }} when the maximum number of unsuccessful attempts is exceeded.

**Guidance:** The need to limit unsuccessful logon attempts and take subsequent action when the maximum number of attempts is exceeded applies regardless of whether the logon occurs via a local or network connection. Due to the potential for denial of service, automatic lockouts initiated by systems are usually t

**Related:** AC-2, AC-9, AU-2, AU-6, IA-5

**Assessment Objectives:**
- ac-7_obj.a a limit of {{ insert: param, ac-07_odp.01 }} consecutive invalid logon attempts by a user during {{ insert: param, ac-07_odp.02 }} is enforced;
- ac-7_obj.b automatically {{ insert: param, ac-07_odp.03 }} when the maximum number of unsuccessful attempts is exceeded.

---

## AC-8: System Use Notification
(ac-8_smt.a) Display {{ insert: param, ac-08_odp.01 }} to users before granting access to the system that provides privacy and security notices consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines and state that:
    (ac-8_smt.a.1) Users are accessing a U.S. Government system;
    (ac-8_smt.a.2) System usage may be monitored, recorded, and subject to audit;
    (ac-8_smt.a.3) Unauthorized use of the system is prohibited and subject to cr

**Guidance:** System use notifications can be implemented using messages or warning banners displayed before individuals log in to systems. System use notifications are used only for access via logon interfaces with human users. Notifications are not required when human interfaces do not exist. Based on an assess

**Related:** AC-14, PL-4, SI-4

**Assessment Objectives:**
- ac-8_obj.a {{ insert: param, ac-08_odp.01 }} is displayed to users before granting access to the system that provides privacy and security notices consistent with applicable laws, Executive Orders, directives, regulations, policies, standards, and guidelines;
- ac-8_obj.b the notification message or banner is retained on the screen until users acknowledge the usage conditions and take explicit actions to log on to or further access the system;
- ac-8_obj.c

---

## AC-9: Previous Logon Notification
Notify the user, upon successful logon to the system, of the date and time of the last logon.

**Guidance:** Previous logon notification is applicable to system access via human user interfaces and access to systems that occurs in other types of architectures. Information about the last successful logon allows the user to recognize if the date and time provided is not consistent with the user’s last access

**Related:** AC-7, PL-4

---

## AC-10: Concurrent Session Control
Limit the number of concurrent sessions for each {{ insert: param, ac-10_odp.01 }} to {{ insert: param, ac-10_odp.02 }}.

**Guidance:** Organizations may define the maximum number of concurrent sessions for system accounts globally, by account type, by account, or any combination thereof. For example, organizations may limit the number of concurrent sessions for system administrators or other individuals working in particularly sens

**Related:** SC-23

---

## AC-11: Device Lock
(ac-11_smt.a) Prevent further access to the system by {{ insert: param, ac-11_odp.01 }} ; and
  (ac-11_smt.b) Retain the device lock until the user reestablishes access using established identification and authentication procedures.

**Guidance:** Device locks are temporary actions taken to prevent logical access to organizational systems when users stop work and move away from the immediate vicinity of those systems but do not want to log out because of the temporary nature of their absences. Device locks can be implemented at the operating

**Related:** AC-2, AC-7, IA-11, PL-4

**Assessment Objectives:**
- ac-11_obj.a further access to the system is prevented by {{ insert: param, ac-11_odp.01 }};
- ac-11_obj.b device lock is retained until the user re-establishes access using established identification and authentication procedures.

---

## AC-12: Session Termination
Automatically terminate a user session after {{ insert: param, ac-12_odp }}.

**Guidance:** Session termination addresses the termination of user-initiated logical sessions (in contrast to [SC-10](#sc-10) , which addresses the termination of network connections associated with communications sessions (i.e., network disconnect)). A logical session (for local, network, and remote access) is

**Related:** MA-4, SC-10, SC-23

---

## AC-14: Permitted Actions Without Identification or Authentication
(ac-14_smt.a) Identify {{ insert: param, ac-14_odp }} that can be performed on the system without identification or authentication consistent with organizational mission and business functions; and
  (ac-14_smt.b) Document and provide supporting rationale in the security plan for the system, user actions not requiring identification or authentication.

**Guidance:** Specific user actions may be permitted without identification or authentication if organizations determine that identification and authentication are not required for the specified user actions. Organizations may allow a limited number of user actions without identification or authentication, includ

**Related:** AC-8, IA-2, PL-2

**Assessment Objectives:**
- ac-14_obj.a {{ insert: param, ac-14_odp }} that can be performed on the system without identification or authentication consistent with organizational mission and business functions are identified;
- ac-14_obj.b

---

## AC-16: Security and Privacy Attributes
(ac-16_smt.a) Provide the means to associate {{ insert: param, ac-16_prm_1 }} with {{ insert: param, ac-16_prm_2 }} for information in storage, in process, and/or in transmission;
  (ac-16_smt.b) Ensure that the attribute associations are made and retained with the information;
  (ac-16_smt.c) Establish the following permitted security and privacy attributes from the attributes defined in [AC-16a](#ac-16_smt.a) for {{ insert: param, ac-16_prm_3 }}: {{ insert: param, ac-16_prm_4 }};
  (ac-16_smt.

**Guidance:** Information is represented internally within systems using abstractions known as data structures. Internal data structures can represent different types of entities, both active and passive. Active entities, also known as subjects, are typically associated with individuals, devices, or processes act

**Related:** AC-3, AC-4, AC-6, AC-21, AC-25, AU-2, AU-10, MP-3, PE-22, PT-2, PT-3, PT-4, SC-11, SC-16, SI-12, SI-18

**Assessment Objectives:**
- ac-16_obj.a
- ac-16_obj.b
- ac-16_obj.c
- ac-16_obj.d the following permitted attribute values or ranges for each of the established attributes are determined: {{ insert: param, ac-16_odp.09 }};
- ac-16_obj.e changes to attributes are audited;
- ac-16_obj.f

---

## AC-17: Remote Access
(ac-17_smt.a) Establish and document usage restrictions, configuration/connection requirements, and implementation guidance for each type of remote access allowed; and
  (ac-17_smt.b) Authorize each type of remote access to the system prior to allowing such connections.

**Guidance:** Remote access is access to organizational systems (or processes acting on behalf of users) that communicate through external networks such as the Internet. Types of remote access include dial-up, broadband, and wireless. Organizations use encrypted virtual private networks (VPNs) to enhance confiden

**Related:** AC-2, AC-3, AC-4, AC-18, AC-19, AC-20, CA-3, CM-10, IA-2, IA-3, IA-8, MA-4, PE-17, PL-2, PL-4, SC-10, SC-12, SC-13, SI-4

**Assessment Objectives:**
- ac-17_obj.a
- ac-17_obj.b each type of remote access to the system is authorized prior to allowing such connections.

---

## AC-18: Wireless Access
(ac-18_smt.a) Establish configuration requirements, connection requirements, and implementation guidance for each type of wireless access; and
  (ac-18_smt.b) Authorize each type of wireless access to the system prior to allowing such connections.

**Guidance:** Wireless technologies include microwave, packet radio (ultra-high frequency or very high frequency), 802.11x, and Bluetooth. Wireless networks use authentication protocols that provide authenticator protection and mutual authentication.

**Related:** AC-2, AC-3, AC-17, AC-19, CA-9, CM-7, IA-2, IA-3, IA-8, PL-4, SC-40, SC-43, SI-4

**Assessment Objectives:**
- ac-18_obj.a
- ac-18_obj.b each type of wireless access to the system is authorized prior to allowing such connections.

---

## AC-19: Access Control for Mobile Devices
(ac-19_smt.a) Establish configuration requirements, connection requirements, and implementation guidance for organization-controlled mobile devices, to include when such devices are outside of controlled areas; and
  (ac-19_smt.b) Authorize the connection of mobile devices to organizational systems.

**Guidance:** A mobile device is a computing device that has a small form factor such that it can easily be carried by a single individual; is designed to operate without a physical connection; possesses local, non-removable or removable data storage; and includes a self-contained power source. Mobile device func

**Related:** AC-3, AC-4, AC-7, AC-11, AC-17, AC-18, AC-20, CA-9, CM-2, CM-6, IA-2, IA-3, MP-2, MP-4, MP-5, MP-7, PL-4, SC-7, SC-34, SC-43, SI-3, SI-4

**Assessment Objectives:**
- ac-19_obj.a
- ac-19_obj.b the connection of mobile devices to organizational systems is authorized.

---

## AC-20: Use of External Systems
(ac-20_smt.a) {{ insert: param, ac-20_odp.01 }} , consistent with the trust relationships established with other organizations owning, operating, and/or maintaining external systems, allowing authorized individuals to:
    (ac-20_smt.a.1) Access the system from external systems; and
    (ac-20_smt.a.2) Process, store, or transmit organization-controlled information using external systems; or
  (ac-20_smt.b) Prohibit the use of {{ insert: param, ac-20_odp.04 }}.

**Guidance:** External systems are systems that are used by but not part of organizational systems, and for which the organization has no direct control over the implementation of required controls or the assessment of control effectiveness. External systems include personally owned systems, components, or device

**Related:** AC-2, AC-3, AC-17, AC-19, CA-3, PL-2, PL-4, SA-9, SC-7

**Assessment Objectives:**
- ac-20_obj.a
- ac-20_obj.b the use of {{ insert: param, ac-20_odp.04 }} is prohibited (if applicable).

---

## AC-21: Information Sharing
(ac-21_smt.a) Enable authorized users to determine whether access authorizations assigned to a sharing partner match the information’s access and use restrictions for {{ insert: param, ac-21_odp.01 }} ; and
  (ac-21_smt.b) Employ {{ insert: param, ac-21_odp.02 }} to assist users in making information sharing and collaboration decisions.

**Guidance:** Information sharing applies to information that may be restricted in some manner based on some formal or administrative determination. Examples of such information include, contract-sensitive information, classified information related to special access programs or compartments, privileged informati

**Related:** AC-3, AC-4, AC-16, PT-2, PT-7, RA-3, SC-15

**Assessment Objectives:**
- ac-21_obj.a authorized users are enabled to determine whether access authorizations assigned to a sharing partner match the information’s access and use restrictions for {{ insert: param, ac-21_odp.01 }};
- ac-21_obj.b {{ insert: param, ac-21_odp.02 }} are employed to assist users in making information-sharing and collaboration decisions.

---

## AC-22: Publicly Accessible Content
(ac-22_smt.a) Designate individuals authorized to make information publicly accessible;
  (ac-22_smt.b) Train authorized individuals to ensure that publicly accessible information does not contain nonpublic information;
  (ac-22_smt.c) Review the proposed content of information prior to posting onto the publicly accessible system to ensure that nonpublic information is not included; and
  (ac-22_smt.d) Review the content on the publicly accessible system for nonpublic information {{ insert: para

**Guidance:** In accordance with applicable laws, executive orders, directives, policies, regulations, standards, and guidelines, the public is not authorized to have access to nonpublic information, including information protected under the [PRIVACT](#18e71fec-c6fd-475a-925a-5d8495cf8455) and proprietary informa

**Related:** AC-3, AT-2, AT-3, AU-13

**Assessment Objectives:**
- ac-22_obj.a designated individuals are authorized to make information publicly accessible;
- ac-22_obj.b authorized individuals are trained to ensure that publicly accessible information does not contain non-public information;
- ac-22_obj.c the proposed content of information is reviewed prior to posting onto the publicly accessible system to ensure that non-public information is not included;
- ac-22_obj.d

---

## AC-23: Data Mining Protection
Employ {{ insert: param, ac-23_odp.01 }} for {{ insert: param, ac-23_odp.02 }} to detect and protect against unauthorized data mining.

**Guidance:** Data mining is an analytical process that attempts to find correlations or patterns in large data sets for the purpose of data or knowledge discovery. Data storage objects include database records and database fields. Sensitive information can be extracted from data mining operations. When informati

**Related:** PM-12, PT-2

---

## AC-24: Access Control Decisions
{{ insert: param, ac-24_odp.01 }} to ensure {{ insert: param, ac-24_odp.02 }} are applied to each access request prior to access enforcement.

**Guidance:** Access control decisions (also known as authorization decisions) occur when authorization information is applied to specific accesses. In contrast, access enforcement occurs when systems enforce access control decisions. While it is common to have access control decisions and access enforcement impl

**Related:** AC-2, AC-3

---

## AC-25: Reference Monitor
Implement a reference monitor for {{ insert: param, ac-25_odp }} that is tamperproof, always invoked, and small enough to be subject to analysis and testing, the completeness of which can be assured.

**Guidance:** A reference monitor is a set of design requirements on a reference validation mechanism that, as a key component of an operating system, enforces an access control policy over all subjects and objects. A reference validation mechanism is always invoked, tamper-proof, and small enough to be subject t

**Related:** AC-3, AC-16, SA-8, SA-17, SC-3, SC-11, SC-39, SI-13
