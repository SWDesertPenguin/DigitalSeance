# NIST 800-53: SI — System and Information Integrity

## SI-1: Policy and Procedures
(si-1_smt.a) Develop, document, and disseminate to {{ insert: param, si-1_prm_1 }}:
    (si-1_smt.a.1) {{ insert: param, si-01_odp.03 }} system and information integrity policy that:
      (si-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (si-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (si-1_smt

**Guidance:** System and information integrity policy and procedures address the controls in the SI family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and pri

**Related:** PM-9, PS-8, SA-8, SI-12

**Assessment Objectives:**
- si-1_obj.a
- si-1_obj.b the {{ insert: param, si-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the system and information integrity policy and procedures;
- si-1_obj.c

---

## SI-2: Flaw Remediation
(si-2_smt.a) Identify, report, and correct system flaws;
  (si-2_smt.b) Test software and firmware updates related to flaw remediation for effectiveness and potential side effects before installation;
  (si-2_smt.c) Install security-relevant software and firmware updates within {{ insert: param, si-02_odp }} of the release of the updates; and
  (si-2_smt.d) Incorporate flaw remediation into the organizational configuration management process.

**Guidance:** The need to remediate system flaws applies to all types of software and firmware. Organizations identify systems affected by software flaws, including potential vulnerabilities resulting from those flaws, and report this information to designated organizational personnel with information security an

**Related:** CA-5, CM-3, CM-4, CM-5, CM-6, CM-8, MA-2, RA-5, SA-8, SA-10, SA-11, SI-3, SI-5, SI-7, SI-11

**Assessment Objectives:**
- si-2_obj.a
- si-2_obj.b
- si-2_obj.c
- si-2_obj.d flaw remediation is incorporated into the organizational configuration management process.

---

## SI-3: Malicious Code Protection
(si-3_smt.a) Implement {{ insert: param, si-03_odp.01 }} malicious code protection mechanisms at system entry and exit points to detect and eradicate malicious code;
  (si-3_smt.b) Automatically update malicious code protection mechanisms as new releases are available in accordance with organizational configuration management policy and procedures;
  (si-3_smt.c) Configure malicious code protection mechanisms to:
    (si-3_smt.c.1) Perform periodic scans of the system {{ insert: param, si-03_odp

**Guidance:** System entry and exit points include firewalls, remote access servers, workstations, electronic mail servers, web servers, proxy servers, notebook computers, and mobile devices. Malicious code includes viruses, worms, Trojan horses, and spyware. Malicious code can also be encoded in various formats

**Related:** AC-4, AC-19, CM-3, CM-8, IR-4, MA-3, MA-4, PL-9, RA-5, SC-7, SC-23, SC-26, SC-28, SC-44, SI-2, SI-4, SI-7, SI-8, SI-15

**Assessment Objectives:**
- si-3_obj.a
- si-3_obj.b malicious code protection mechanisms are updated automatically as new releases are available in accordance with organizational configuration management policy and procedures;
- si-3_obj.c
- si-3_obj.d the receipt of false positives during malicious code detection and eradication and the resulting potential impact on the availability of the system are addressed.

---

## SI-4: System Monitoring
(si-4_smt.a) Monitor the system to detect:
    (si-4_smt.a.1) Attacks and indicators of potential attacks in accordance with the following monitoring objectives: {{ insert: param, si-04_odp.01 }} ; and
    (si-4_smt.a.2) Unauthorized local, network, and remote connections;
  (si-4_smt.b) Identify unauthorized use of the system through the following techniques and methods: {{ insert: param, si-04_odp.02 }};
  (si-4_smt.c) Invoke internal monitoring capabilities or deploy monitoring devices:
    (

**Guidance:** System monitoring includes external and internal monitoring. External monitoring includes the observation of events occurring at external interfaces to the system. Internal monitoring includes the observation of events occurring within the system. Organizations monitor systems by observing audit act

**Related:** AC-2, AC-3, AC-4, AC-8, AC-17, AU-2, AU-6, AU-7, AU-9, AU-12, AU-13, AU-14, CA-7, CM-3, CM-6, CM-8, CM-11, IA-10, IR-4, MA-3, MA-4, PL-9, PM-12, RA-5, RA-10, SC-5, SC-7, SC-18, SC-26, SC-31, SC-35, SC-36, SC-37, SC-43, SI-3, SI-6, SI-7, SR-9, SR-10

**Assessment Objectives:**
- si-4_obj.a
- si-4_obj.b unauthorized use of the system is identified through {{ insert: param, si-04_odp.02 }};
- si-4_obj.c
- si-4_obj.d
- si-4_obj.e the level of system monitoring activity is adjusted when there is a change in risk to organizational operations and assets, individuals, other organizations, or the Nation;
- si-4_obj.f a legal opinion regarding system monitoring activities is obtained;
- si-4_obj.g {{ insert: param, si-04_odp.03 }} is provided to {{ insert: param, si-04_odp.04 }} {{ insert: param, si-04_odp.05 }}.

---

## SI-5: Security Alerts, Advisories, and Directives
(si-5_smt.a) Receive system security alerts, advisories, and directives from {{ insert: param, si-05_odp.01 }} on an ongoing basis;
  (si-5_smt.b) Generate internal security alerts, advisories, and directives as deemed necessary;
  (si-5_smt.c) Disseminate security alerts, advisories, and directives to: {{ insert: param, si-05_odp.02 }} ; and
  (si-5_smt.d) Implement security directives in accordance with established time frames, or notify the issuing organization of the degree of noncompliance.

**Guidance:** The Cybersecurity and Infrastructure Security Agency (CISA) generates security alerts and advisories to maintain situational awareness throughout the Federal Government. Security directives are issued by OMB or other designated organizations with the responsibility and authority to issue such direct

**Related:** PM-15, RA-5, SI-2

**Assessment Objectives:**
- si-5_obj.a system security alerts, advisories, and directives are received from {{ insert: param, si-05_odp.01 }} on an ongoing basis;
- si-5_obj.b internal security alerts, advisories, and directives are generated as deemed necessary;
- si-5_obj.c security alerts, advisories, and directives are disseminated to {{ insert: param, si-05_odp.02 }};
- si-5_obj.d security directives are implemented in accordance with established time frames or if the issuing organization is notified of the degree of noncompliance.

---

## SI-6: Security and Privacy Function Verification
(si-6_smt.a) Verify the correct operation of {{ insert: param, si-6_prm_1 }};
  (si-6_smt.b) Perform the verification of the functions specified in SI-6a {{ insert: param, si-06_odp.03 }};
  (si-6_smt.c) Alert {{ insert: param, si-06_odp.06 }} to failed security and privacy verification tests; and
  (si-6_smt.d) {{ insert: param, si-06_odp.07 }} when anomalies are discovered.

**Guidance:** Transitional states for systems include system startup, restart, shutdown, and abort. System notifications include hardware indicator lights, electronic alerts to system administrators, and messages to local computer consoles. In contrast to security function verification, privacy function verificat

**Related:** CA-7, CM-4, CM-6, SI-7

**Assessment Objectives:**
- si-6_obj.a
- si-6_obj.b
- si-6_obj.c
- si-6_obj.d {{ insert: param, si-06_odp.07 }} is/are initiated when anomalies are discovered.

---

## SI-7: Software, Firmware, and Information Integrity
(si-7_smt.a) Employ integrity verification tools to detect unauthorized changes to the following software, firmware, and information: {{ insert: param, si-7_prm_1 }} ; and
  (si-7_smt.b) Take the following actions when unauthorized changes to the software, firmware, and information are detected: {{ insert: param, si-7_prm_2 }}.

**Guidance:** Unauthorized changes to software, firmware, and information can occur due to errors or malicious activity. Software includes operating systems (with key internal components, such as kernels or drivers), middleware, and applications. Firmware interfaces include Unified Extensible Firmware Interface (

**Related:** AC-4, CM-3, CM-7, CM-8, MA-3, MA-4, RA-5, SA-8, SA-9, SA-10, SC-8, SC-12, SC-13, SC-28, SC-37, SI-3, SR-3, SR-4, SR-5, SR-6, SR-9, SR-10, SR-11

**Assessment Objectives:**
- si-7_obj.a
- si-7_obj.b

---

## SI-8: Spam Protection
(si-8_smt.a) Employ spam protection mechanisms at system entry and exit points to detect and act on unsolicited messages; and
  (si-8_smt.b) Update spam protection mechanisms when new releases are available in accordance with organizational configuration management policy and procedures.

**Guidance:** System entry and exit points include firewalls, remote-access servers, electronic mail servers, web servers, proxy servers, workstations, notebook computers, and mobile devices. Spam can be transported by different means, including email, email attachments, and web accesses. Spam protection mechanis

**Related:** PL-9, SC-5, SC-7, SC-38, SI-3, SI-4

**Assessment Objectives:**
- si-8_obj.a
- si-8_obj.b spam protection mechanisms are updated when new releases are available in accordance with organizational configuration management policies and procedures.

---

## SI-10: Information Input Validation
Check the validity of the following information inputs: {{ insert: param, si-10_odp }}.

**Guidance:** Checking the valid syntax and semantics of system inputs—including character set, length, numerical range, and acceptable values—verifies that inputs match specified definitions for format and content. For example, if the organization specifies that numerical values between 1-100 are the only accept

---

## SI-11: Error Handling
(si-11_smt.a) Generate error messages that provide information necessary for corrective actions without revealing information that could be exploited; and
  (si-11_smt.b) Reveal error messages only to {{ insert: param, si-11_odp }}.

**Guidance:** Organizations consider the structure and content of error messages. The extent to which systems can handle error conditions is guided and informed by organizational policy and operational requirements. Exploitable information includes stack traces and implementation details; erroneous logon attempts

**Related:** AU-2, AU-3, SC-31, SI-2, SI-15

**Assessment Objectives:**
- si-11_obj.a error messages that provide the information necessary for corrective actions are generated without revealing information that could be exploited;
- si-11_obj.b error messages are revealed only to {{ insert: param, si-11_odp }}.

---

## SI-12: Information Management and Retention
Manage and retain information within the system and information output from the system in accordance with applicable laws, executive orders, directives, regulations, policies, standards, guidelines and operational requirements.

**Guidance:** Information management and retention requirements cover the full life cycle of information, in some cases extending beyond system disposal. Information to be retained may also include policies, procedures, plans, reports, data output from control implementation, and other types of administrative inf

**Related:** AC-16, AU-5, AU-11, CA-2, CA-3, CA-5, CA-6, CA-7, CA-9, CM-5, CM-9, CP-2, IR-8, MP-2, MP-3, MP-4, MP-6, PL-2, PL-4, PM-4, PM-8, PM-9, PS-2, PS-6, PT-2, PT-3, RA-2, RA-3, SA-5, SA-8, SR-2

**Assessment Objectives:**
- si-12_obj-1 information within the system is managed in accordance with applicable laws, Executive Orders, directives, regulations, policies, standards, guidelines, and operational requirements;
- si-12_obj-2 information within the system is retained in accordance with applicable laws, Executive Orders, directives, regulations, policies, standards, guidelines, and operational requirements;
- si-12_obj-3 information output from the system is managed in accordance with applicable laws, Executive Orders, directives, regulations, policies, standards, guidelines, and operational requirements;
- si-12_obj-4 information output from the system is retained in accordance with applicable laws, Executive Orders, directives, regulations, policies, standards, guidelines, and operational requirements.

---

## SI-13: Predictable Failure Prevention
(si-13_smt.a) Determine mean time to failure (MTTF) for the following system components in specific environments of operation: {{ insert: param, si-13_odp.01 }} ; and
  (si-13_smt.b) Provide substitute system components and a means to exchange active and standby components in accordance with the following criteria: {{ insert: param, si-13_odp.02 }}.

**Guidance:** While MTTF is primarily a reliability issue, predictable failure prevention is intended to address potential failures of system components that provide security capabilities. Failure rates reflect installation-specific consideration rather than the industry-average. Organizations define the criteria

**Related:** CP-2, CP-10, CP-13, MA-2, MA-6, SA-8, SC-6

**Assessment Objectives:**
- si-13_obj.a mean time to failure (MTTF) is determined for {{ insert: param, si-13_odp.01 }} in specific environments of operation;
- si-13_obj.b substitute system components and a means to exchange active and standby components are provided in accordance with {{ insert: param, si-13_odp.02 }}.

---

## SI-14: Non-persistence
Implement non-persistent {{ insert: param, si-14_odp.01 }} that are initiated in a known state and terminated {{ insert: param, si-14_odp.02 }}.

**Guidance:** Implementation of non-persistent components and services mitigates risk from advanced persistent threats (APTs) by reducing the targeting capability of adversaries (i.e., window of opportunity and available attack surface) to initiate and complete attacks. By implementing the concept of non-persiste

**Related:** SC-30, SC-34, SI-21

**Assessment Objectives:**
- si-14_obj-1 non-persistent {{ insert: param, si-14_odp.01 }} that are initiated in a known state are implemented;
- si-14_obj-2 non-persistent {{ insert: param, si-14_odp.01 }} are terminated {{ insert: param, si-14_odp.02 }}.

---

## SI-15: Information Output Filtering
Validate information output from the following software programs and/or applications to ensure that the information is consistent with the expected content: {{ insert: param, si-15_odp }}.

**Guidance:** Certain types of attacks, including SQL injections, produce output results that are unexpected or inconsistent with the output results that would be expected from software programs or applications. Information output filtering focuses on detecting extraneous content, preventing such extraneous conte

**Related:** SI-3, SI-4, SI-11

---

## SI-16: Memory Protection
Implement the following controls to protect the system memory from unauthorized code execution: {{ insert: param, si-16_odp }}.

**Guidance:** Some adversaries launch attacks with the intent of executing code in non-executable regions of memory or in memory locations that are prohibited. Controls employed to protect memory include data execution prevention and address space layout randomization. Data execution prevention controls can eithe

**Related:** AC-25, SC-3, SI-7

---

## SI-17: Fail-safe Procedures
Implement the indicated fail-safe procedures when the indicated failures occur: {{ insert: param, si-17_prm_1 }}.

**Guidance:** Failure conditions include the loss of communications among critical system components or between system components and operational facilities. Fail-safe procedures include alerting operator personnel and providing specific instructions on subsequent steps to take. Subsequent steps may include doing

**Related:** CP-12, CP-13, SC-24, SI-13

---

## SI-18: Personally Identifiable Information Quality Operations
(si-18_smt.a) Check the accuracy, relevance, timeliness, and completeness of personally identifiable information across the information life cycle {{ insert: param, si-18_prm_1 }} ; and
  (si-18_smt.b) Correct or delete inaccurate or outdated personally identifiable information.

**Guidance:** Personally identifiable information quality operations include the steps that organizations take to confirm the accuracy and relevance of personally identifiable information throughout the information life cycle. The information life cycle includes the creation, collection, use, processing, storage,

**Related:** PM-22, PM-24, PT-2, SI-4

**Assessment Objectives:**
- si-18_obj.a
- si-18_obj.b inaccurate or outdated personally identifiable information is corrected or deleted.

---

## SI-19: De-identification
(si-19_smt.a) Remove the following elements of personally identifiable information from datasets: {{ insert: param, si-19_odp.01 }} ; and
  (si-19_smt.b) Evaluate {{ insert: param, si-19_odp.02 }} for effectiveness of de-identification.

**Guidance:** De-identification is the general term for the process of removing the association between a set of identifying data and the data subject. Many datasets contain information about individuals that can be used to distinguish or trace an individual’s identity, such as name, social security number, date

**Related:** MP-6, PM-22, PM-23, PM-24, RA-2, SI-12

**Assessment Objectives:**
- si-19_obj.a {{ insert: param, si-19_odp.01 }} are removed from datasets;
- si-19_obj.b the effectiveness of de-identification is evaluated {{ insert: param, si-19_odp.02 }}.

---

## SI-20: Tainting
Embed data or capabilities in the following systems or system components to determine if organizational data has been exfiltrated or improperly removed from the organization: {{ insert: param, si-20_odp }}.

**Guidance:** Many cyber-attacks target organizational information, or information that the organization holds on behalf of other entities (e.g., personally identifiable information), and exfiltrate that data. In addition, insider attacks and erroneous user procedures can remove information from the system that i

**Related:** AU-13

---

## SI-21: Information Refresh
Refresh {{ insert: param, si-21_odp.01 }} at {{ insert: param, si-21_odp.02 }} or generate the information on demand and delete the information when no longer needed.

**Guidance:** Retaining information for longer than it is needed makes it an increasingly valuable and enticing target for adversaries. Keeping information available for the minimum period of time needed to support organizational missions or business functions reduces the opportunity for adversaries to compromise

**Related:** SI-14

---

## SI-22: Information Diversity
(si-22_smt.a) Identify the following alternative sources of information for {{ insert: param, si-22_odp.02 }}: {{ insert: param, si-22_odp.01 }} ; and
  (si-22_smt.b) Use an alternative information source for the execution of essential functions or services on {{ insert: param, si-22_odp.03 }} when the primary source of information is corrupted or unavailable.

**Guidance:** Actions taken by a system service or a function are often driven by the information it receives. Corruption, fabrication, modification, or deletion of that information could impact the ability of the service function to properly carry out its intended actions. By having multiple sources of input, th

**Assessment Objectives:**
- si-22_obj.a {{ insert: param, si-22_odp.01 }} for {{ insert: param, si-22_odp.02 }} are identified;
- si-22_obj.b an alternative information source is used for the execution of essential functions or services on {{ insert: param, si-22_odp.03 }} when the primary source of information is corrupted or unavailable.

---

## SI-23: Information Fragmentation
Based on {{ insert: param, si-23_odp.01 }}:
  (si-23_smt.a) Fragment the following information: {{ insert: param, si-23_odp.02 }} ; and
  (si-23_smt.b) Distribute the fragmented information across the following systems or system components: {{ insert: param, si-23_odp.03 }}.

**Guidance:** One objective of the advanced persistent threat is to exfiltrate valuable information. Once exfiltrated, there is generally no way for the organization to recover the lost information. Therefore, organizations may consider dividing the information into disparate elements and distributing those eleme

**Assessment Objectives:**
- si-23_obj.a under {{ insert: param, si-23_odp.01 }}, {{ insert: param, si-23_odp.02 }} is fragmented;
- si-23_obj.b under {{ insert: param, si-23_odp.01 }} , the fragmented information is distributed across {{ insert: param, si-23_odp.03 }}.
