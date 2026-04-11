# NIST 800-53: IR — Incident Response

## IR-1: Policy and Procedures
(ir-1_smt.a) Develop, document, and disseminate to {{ insert: param, ir-1_prm_1 }}:
    (ir-1_smt.a.1) {{ insert: param, ir-01_odp.03 }} incident response policy that:
      (ir-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ir-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (ir-1_smt.a.2) Procedure

**Guidance:** Incident response policy and procedures address the controls in the IR family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance.

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- ir-1_obj.a
- ir-1_obj.b the {{ insert: param, ir-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the incident response policy and procedures;
- ir-1_obj.c

---

## IR-2: Incident Response Training
(ir-2_smt.a) Provide incident response training to system users consistent with assigned roles and responsibilities:
    (ir-2_smt.a.1) Within {{ insert: param, ir-02_odp.01 }} of assuming an incident response role or responsibility or acquiring system access;
    (ir-2_smt.a.2) When required by system changes; and
    (ir-2_smt.a.3) {{ insert: param, ir-02_odp.02 }} thereafter; and
  (ir-2_smt.b) Review and update incident response training content {{ insert: param, ir-02_odp.03 }} and followin

**Guidance:** Incident response training is associated with the assigned roles and responsibilities of organizational personnel to ensure that the appropriate content and level of detail are included in such training. For example, users may only need to know who to call or how to recognize an incident; system adm

**Related:** AT-2, AT-3, AT-4, CP-3, IR-3, IR-4, IR-8, IR-9

**Assessment Objectives:**
- ir-2_obj.a
- ir-2_obj.b

---

## IR-3: Incident Response Testing
Test the effectiveness of the incident response capability for the system {{ insert: param, ir-03_odp.01 }} using the following tests: {{ insert: param, ir-03_odp.02 }}.

**Guidance:** Organizations test incident response capabilities to determine their effectiveness and identify potential weaknesses or deficiencies. Incident response testing includes the use of checklists, walk-through or tabletop exercises, and simulations (parallel or full interrupt). Incident response testing

**Related:** CP-3, CP-4, IR-2, IR-4, IR-8, PM-14

---

## IR-4: Incident Handling
(ir-4_smt.a) Implement an incident handling capability for incidents that is consistent with the incident response plan and includes preparation, detection and analysis, containment, eradication, and recovery;
  (ir-4_smt.b) Coordinate incident handling activities with contingency planning activities;
  (ir-4_smt.c) Incorporate lessons learned from ongoing incident handling activities into incident response procedures, training, and testing, and implement the resulting changes accordingly; and


**Guidance:** Organizations recognize that incident response capabilities are dependent on the capabilities of organizational systems and the mission and business processes being supported by those systems. Organizations consider incident response as part of the definition, design, and development of mission and

**Related:** AC-19, AU-6, AU-7, CM-6, CP-2, CP-3, CP-4, IR-2, IR-3, IR-5, IR-6, IR-8, PE-6, PL-2, PM-12, SA-8, SC-5, SC-7, SI-3, SI-4, SI-7

**Assessment Objectives:**
- ir-4_obj.a
- ir-4_obj.b incident handling activities are coordinated with contingency planning activities;
- ir-4_obj.c
- ir-4_obj.d

---

## IR-5: Incident Monitoring
Track and document incidents.

**Guidance:** Documenting incidents includes maintaining records about each incident, the status of the incident, and other pertinent information necessary for forensics as well as evaluating incident details, trends, and handling. Incident information can be obtained from a variety of sources, including network

**Related:** AU-6, AU-7, IR-4, IR-6, IR-8, PE-6, PM-5, SC-5, SC-7, SI-3, SI-4, SI-7

**Assessment Objectives:**
- ir-5_obj-1 incidents are tracked;
- ir-5_obj-2 incidents are documented.

---

## IR-6: Incident Reporting
(ir-6_smt.a) Require personnel to report suspected incidents to the organizational incident response capability within {{ insert: param, ir-06_odp.01 }} ; and
  (ir-6_smt.b) Report incident information to {{ insert: param, ir-06_odp.02 }}.

**Guidance:** The types of incidents reported, the content and timeliness of the reports, and the designated reporting authorities reflect applicable laws, executive orders, directives, regulations, policies, standards, and guidelines. Incident information can inform risk assessments, control effectiveness assess

**Related:** CM-6, CP-2, IR-4, IR-5, IR-8, IR-9

**Assessment Objectives:**
- ir-6_obj.a personnel is/are required to report suspected incidents to the organizational incident response capability within {{ insert: param, ir-06_odp.01 }};
- ir-6_obj.b incident information is reported to {{ insert: param, ir-06_odp.02 }}.

---

## IR-7: Incident Response Assistance
Provide an incident response support resource, integral to the organizational incident response capability, that offers advice and assistance to users of the system for the handling and reporting of incidents.

**Guidance:** Incident response support resources provided by organizations include help desks, assistance groups, automated ticketing systems to open and track incident response tickets, and access to forensics services or consumer redress services, when required.

**Related:** AT-2, AT-3, IR-4, IR-6, IR-8, PM-22, PM-26, SA-9, SI-18

**Assessment Objectives:**
- ir-7_obj-1 an incident response support resource, integral to the organizational incident response capability, is provided;
- ir-7_obj-2 the incident response support resource offers advice and assistance to users of the system for the response and reporting of incidents.

---

## IR-8: Incident Response Plan
(ir-8_smt.a) Develop an incident response plan that:
    (ir-8_smt.a.1) Provides the organization with a roadmap for implementing its incident response capability;
    (ir-8_smt.a.2) Describes the structure and organization of the incident response capability;
    (ir-8_smt.a.3) Provides a high-level approach for how the incident response capability fits into the overall organization;
    (ir-8_smt.a.4) Meets the unique requirements of the organization, which relate to mission, size, structure,

**Guidance:** It is important that organizations develop and implement a coordinated approach to incident response. Organizational mission and business functions determine the structure of incident response capabilities. As part of the incident response capabilities, organizations consider the coordination and sh

**Related:** AC-2, CP-2, CP-4, IR-4, IR-7, IR-9, PE-6, PL-2, SA-15, SI-12, SR-8

**Assessment Objectives:**
- ir-8_obj.a
- ir-8_obj.b
- ir-8_obj.c the incident response plan is updated to address system and organizational changes or problems encountered during plan implementation, execution, or testing;
- ir-8_obj.d
- ir-8_obj.e

---

## IR-9: Information Spillage Response
Respond to information spills by:
  (ir-9_smt.a) Assigning {{ insert: param, ir-09_odp.01 }} with responsibility for responding to information spills;
  (ir-9_smt.b) Identifying the specific information involved in the system contamination;
  (ir-9_smt.c) Alerting {{ insert: param, ir-09_odp.02 }} of the information spill using a method of communication not associated with the spill;
  (ir-9_smt.d) Isolating the contaminated system or system component;
  (ir-9_smt.e) Eradicating the information

**Guidance:** Information spillage refers to instances where information is placed on systems that are not authorized to process such information. Information spills occur when information that is thought to be a certain classification or impact level is transmitted to a system and subsequently is determined to b

**Related:** CP-2, IR-6, PM-26, PM-27, PT-2, PT-3, PT-7, RA-7

**Assessment Objectives:**
- ir-9_obj.a {{ insert: param, ir-09_odp.01 }} is/are assigned the responsibility to respond to information spills;
- ir-9_obj.b the specific information involved in the system contamination is identified in response to information spills;
- ir-9_obj.c {{ insert: param, ir-09_odp.02 }} is/are alerted of the information spill using a method of communication not associated with the spill;
- ir-9_obj.d the contaminated system or system component is isolated in response to information spills;
- ir-9_obj.e the information is eradicated from the contaminated system or component in response to information spills;
- ir-9_obj.f other systems or system components that may have been subsequently contaminated are identified in response to information spills;
- ir-9_obj.g {{ insert: param, ir-09_odp.03 }} are performed in response to information spills.
