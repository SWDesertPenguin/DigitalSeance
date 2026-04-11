# NIST 800-53: MA — Maintenance

## MA-1: Policy and Procedures
(ma-1_smt.a) Develop, document, and disseminate to {{ insert: param, ma-1_prm_1 }}:
    (ma-1_smt.a.1) {{ insert: param, ma-01_odp.03 }} maintenance policy that:
      (ma-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ma-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (ma-1_smt.a.2) Procedures to f

**Guidance:** Maintenance policy and procedures address the controls in the MA family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance. There

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- ma-1_obj.a
- ma-1_obj.b the {{ insert: param, ma-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the maintenance policy and procedures;
- ma-1_obj.c

---

## MA-2: Controlled Maintenance
(ma-2_smt.a) Schedule, document, and review records of maintenance, repair, and replacement on system components in accordance with manufacturer or vendor specifications and/or organizational requirements;
  (ma-2_smt.b) Approve and monitor all maintenance activities, whether performed on site or remotely and whether the system or system components are serviced on site or removed to another location;
  (ma-2_smt.c) Require that {{ insert: param, ma-02_odp.01 }} explicitly approve the removal of

**Guidance:** Controlling system maintenance addresses the information security aspects of the system maintenance program and applies to all types of maintenance to system components conducted by local or nonlocal entities. Maintenance includes peripherals such as scanners, copiers, and printers. Information nece

**Related:** CM-2, CM-3, CM-4, CM-5, CM-8, MA-4, MP-6, PE-16, SI-2, SR-3, SR-4, SR-11

**Assessment Objectives:**
- ma-2_obj.a
- ma-2_obj.b
- ma-2_obj.c {{ insert: param, ma-02_odp.01 }} is/are required to explicitly approve the removal of the system or system components from organizational facilities for off-site maintenance, repair, or replacement;
- ma-2_obj.d equipment is sanitized to remove {{ insert: param, ma-02_odp.02 }} from associated media prior to removal from organizational facilities for off-site maintenance, repair, or replacement;
- ma-2_obj.e all potentially impacted controls are checked to verify that the controls are still functioning properly following maintenance, repair, or replacement actions;
- ma-2_obj.f {{ insert: param, ma-02_odp.03 }} is included in organizational maintenance records.

---

## MA-3: Maintenance Tools
(ma-3_smt.a) Approve, control, and monitor the use of system maintenance tools; and
  (ma-3_smt.b) Review previously approved system maintenance tools {{ insert: param, ma-03_odp }}.

**Guidance:** Approving, controlling, monitoring, and reviewing maintenance tools address security-related issues associated with maintenance tools that are not within system authorization boundaries and are used specifically for diagnostic and repair actions on organizational systems. Organizations have flexibil

**Related:** MA-2, PE-16

**Assessment Objectives:**
- ma-3_obj.a
- ma-3_obj.b previously approved system maintenance tools are reviewed {{ insert: param, ma-03_odp }}.

---

## MA-4: Nonlocal Maintenance
(ma-4_smt.a) Approve and monitor nonlocal maintenance and diagnostic activities;
  (ma-4_smt.b) Allow the use of nonlocal maintenance and diagnostic tools only as consistent with organizational policy and documented in the security plan for the system;
  (ma-4_smt.c) Employ strong authentication in the establishment of nonlocal maintenance and diagnostic sessions;
  (ma-4_smt.d) Maintain records for nonlocal maintenance and diagnostic activities; and
  (ma-4_smt.e) Terminate session and network

**Guidance:** Nonlocal maintenance and diagnostic activities are conducted by individuals who communicate through either an external or internal network. Local maintenance and diagnostic activities are carried out by individuals who are physically present at the system location and not communicating across a netw

**Related:** AC-2, AC-3, AC-6, AC-17, AU-2, AU-3, IA-2, IA-4, IA-5, IA-8, MA-2, MA-5, PL-2, SC-7, SC-10

**Assessment Objectives:**
- ma-4_obj.a
- ma-4_obj.b
- ma-4_obj.c strong authentication is employed in the establishment of nonlocal maintenance and diagnostic sessions;
- ma-4_obj.d records for nonlocal maintenance and diagnostic activities are maintained;
- ma-4_obj.e

---

## MA-5: Maintenance Personnel
(ma-5_smt.a) Establish a process for maintenance personnel authorization and maintain a list of authorized maintenance organizations or personnel;
  (ma-5_smt.b) Verify that non-escorted personnel performing maintenance on the system possess the required access authorizations; and
  (ma-5_smt.c) Designate organizational personnel with required access authorizations and technical competence to supervise the maintenance activities of personnel who do not possess the required access authorizations.

**Guidance:** Maintenance personnel refers to individuals who perform hardware or software maintenance on organizational systems, while [PE-2](#pe-2) addresses physical access for individuals whose maintenance duties place them within the physical protection perimeter of the systems. Technical competence of super

**Related:** AC-2, AC-3, AC-5, AC-6, IA-2, IA-8, MA-4, MP-2, PE-2, PE-3, PS-7, RA-3

**Assessment Objectives:**
- ma-5_obj.a
- ma-5_obj.b non-escorted personnel performing maintenance on the system possess the required access authorizations;
- ma-5_obj.c organizational personnel with required access authorizations and technical competence is/are designated to supervise the maintenance activities of personnel who do not possess the required access authorizations.

---

## MA-6: Timely Maintenance
Obtain maintenance support and/or spare parts for {{ insert: param, ma-06_odp.01 }} within {{ insert: param, ma-06_odp.02 }} of failure.

**Guidance:** Organizations specify the system components that result in increased risk to organizational operations and assets, individuals, other organizations, or the Nation when the functionality provided by those components is not operational. Organizational actions to obtain maintenance support include havi

**Related:** CM-8, CP-2, CP-7, RA-7, SA-15, SI-13, SR-2, SR-3, SR-4

---

## MA-7: Field Maintenance
Restrict or prohibit field maintenance on {{ insert: param, ma-07_odp.01 }} to {{ insert: param, ma-07_odp.02 }}.

**Guidance:** Field maintenance is the type of maintenance conducted on a system or system component after the system or component has been deployed to a specific site (i.e., operational environment). In certain instances, field maintenance (i.e., local maintenance at the site) may not be executed with the same d

**Related:** MA-2, MA-4, MA-5
