# NIST 800-53: PE — Physical and Environmental Protection

## PE-1: Policy and Procedures
(pe-1_smt.a) Develop, document, and disseminate to {{ insert: param, pe-1_prm_1 }}:
    (pe-1_smt.a.1) {{ insert: param, pe-01_odp.03 }} physical and environmental protection policy that:
      (pe-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (pe-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (pe-

**Guidance:** Physical and environmental protection policy and procedures address the controls in the PE family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security an

**Related:** AT-3, PM-9, PS-8, SI-12

**Assessment Objectives:**
- pe-1_obj.a
- pe-1_obj.b the {{ insert: param, pe-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the physical and environmental protection policy and procedures;
- pe-1_obj.c

---

## PE-2: Physical Access Authorizations
(pe-2_smt.a) Develop, approve, and maintain a list of individuals with authorized access to the facility where the system resides;
  (pe-2_smt.b) Issue authorization credentials for facility access;
  (pe-2_smt.c) Review the access list detailing authorized facility access by individuals {{ insert: param, pe-02_odp }} ; and
  (pe-2_smt.d) Remove individuals from the facility access list when access is no longer required.

**Guidance:** Physical access authorizations apply to employees and visitors. Individuals with permanent physical access authorization credentials are not considered visitors. Authorization credentials include ID badges, identification cards, and smart cards. Organizations determine the strength of authorization

**Related:** AT-3, AU-9, IA-4, MA-5, MP-2, PE-3, PE-4, PE-5, PE-8, PM-12, PS-3, PS-4, PS-5, PS-6

**Assessment Objectives:**
- pe-2_obj.a
- pe-2_obj.b authorization credentials are issued for facility access;
- pe-2_obj.c the access list detailing authorized facility access by individuals is reviewed {{ insert: param, pe-02_odp }};
- pe-2_obj.d individuals are removed from the facility access list when access is no longer required.

---

## PE-3: Physical Access Control
(pe-3_smt.a) Enforce physical access authorizations at {{ insert: param, pe-03_odp.01 }} by:
    (pe-3_smt.a.1) Verifying individual access authorizations before granting access to the facility; and
    (pe-3_smt.a.2) Controlling ingress and egress to the facility using {{ insert: param, pe-03_odp.02 }};
  (pe-3_smt.b) Maintain physical access audit logs for {{ insert: param, pe-03_odp.04 }};
  (pe-3_smt.c) Control access to areas within the facility designated as publicly accessible by implemen

**Guidance:** Physical access control applies to employees and visitors. Individuals with permanent physical access authorizations are not considered visitors. Physical access controls for publicly accessible areas may include physical access control logs/records, guards, or physical access devices and barriers t

**Related:** AT-3, AU-2, AU-6, AU-9, AU-13, CP-10, IA-3, IA-8, MA-5, MP-2, MP-4, PE-2, PE-4, PE-5, PE-8, PS-2, PS-3, PS-6, PS-7, RA-3, SC-28, SI-4, SR-3

**Assessment Objectives:**
- pe-3_obj.a
- pe-3_obj.b physical access audit logs are maintained for {{ insert: param, pe-03_odp.04 }};
- pe-3_obj.c access to areas within the facility designated as publicly accessible are maintained by implementing {{ insert: param, pe-03_odp.05 }};
- pe-3_obj.d
- pe-3_obj.e
- pe-3_obj.f {{ insert: param, pe-03_odp.07 }} are inventoried {{ insert: param, pe-03_odp.08 }};
- pe-3_obj.g

---

## PE-4: Access Control for Transmission
Control physical access to {{ insert: param, pe-04_odp.01 }} within organizational facilities using {{ insert: param, pe-04_odp.02 }}.

**Guidance:** Security controls applied to system distribution and transmission lines prevent accidental damage, disruption, and physical tampering. Such controls may also be necessary to prevent eavesdropping or modification of unencrypted transmissions. Security controls used to control physical access to syste

**Related:** AT-3, IA-4, MP-2, MP-4, PE-2, PE-3, PE-5, PE-9, SC-7, SC-8

---

## PE-5: Access Control for Output Devices
Control physical access to output from {{ insert: param, pe-05_odp }} to prevent unauthorized individuals from obtaining the output.

**Guidance:** Controlling physical access to output devices includes placing output devices in locked rooms or other secured areas with keypad or card reader access controls and allowing access to authorized individuals only, placing output devices in locations that can be monitored by personnel, installing monit

**Related:** PE-2, PE-3, PE-4, PE-18

---

## PE-6: Monitoring Physical Access
(pe-6_smt.a) Monitor physical access to the facility where the system resides to detect and respond to physical security incidents;
  (pe-6_smt.b) Review physical access logs {{ insert: param, pe-06_odp.01 }} and upon occurrence of {{ insert: param, pe-06_odp.02 }} ; and
  (pe-6_smt.c) Coordinate results of reviews and investigations with the organizational incident response capability.

**Guidance:** Physical access monitoring includes publicly accessible areas within organizational facilities. Examples of physical access monitoring include the employment of guards, video surveillance equipment (i.e., cameras), and sensor devices. Reviewing physical access logs can help identify suspicious activ

**Related:** AU-2, AU-6, AU-9, AU-12, CA-7, CP-10, IR-4, IR-8

**Assessment Objectives:**
- pe-6_obj.a physical access to the facility where the system resides is monitored to detect and respond to physical security incidents;
- pe-6_obj.b
- pe-6_obj.c

---

## PE-8: Visitor Access Records
(pe-8_smt.a) Maintain visitor access records to the facility where the system resides for {{ insert: param, pe-08_odp.01 }};
  (pe-8_smt.b) Review visitor access records {{ insert: param, pe-08_odp.02 }} ; and
  (pe-8_smt.c) Report anomalies in visitor access records to {{ insert: param, pe-08_odp.03 }}.

**Guidance:** Visitor access records include the names and organizations of individuals visiting, visitor signatures, forms of identification, dates of access, entry and departure times, purpose of visits, and the names and organizations of individuals visited. Access record reviews determine if access authorizat

**Related:** PE-2, PE-3, PE-6

**Assessment Objectives:**
- pe-8_obj.a visitor access records for the facility where the system resides are maintained for {{ insert: param, pe-08_odp.01 }};
- pe-8_obj.b visitor access records are reviewed {{ insert: param, pe-08_odp.02 }};
- pe-8_obj.c visitor access records anomalies are reported to {{ insert: param, pe-08_odp.03 }}.

---

## PE-9: Power Equipment and Cabling
Protect power equipment and power cabling for the system from damage and destruction.

**Guidance:** Organizations determine the types of protection necessary for the power equipment and cabling employed at different locations that are both internal and external to organizational facilities and environments of operation. Types of power equipment and cabling include internal cabling and uninterrupta

**Related:** PE-4

**Assessment Objectives:**
- pe-9_obj-1 power equipment for the system is protected from damage and destruction;
- pe-9_obj-2 power cabling for the system is protected from damage and destruction.

---

## PE-10: Emergency Shutoff
(pe-10_smt.a) Provide the capability of shutting off power to {{ insert: param, pe-10_odp.01 }} in emergency situations;
  (pe-10_smt.b) Place emergency shutoff switches or devices in {{ insert: param, pe-10_odp.02 }} to facilitate access for authorized personnel; and
  (pe-10_smt.c) Protect emergency power shutoff capability from unauthorized activation.

**Guidance:** Emergency power shutoff primarily applies to organizational facilities that contain concentrations of system resources, including data centers, mainframe computer rooms, server rooms, and areas with computer-controlled machinery.

**Related:** PE-15

**Assessment Objectives:**
- pe-10_obj.a the capability to shut off power to {{ insert: param, pe-10_odp.01 }} in emergency situations is provided;
- pe-10_obj.b emergency shutoff switches or devices are placed in {{ insert: param, pe-10_odp.02 }} to facilitate access for authorized personnel;
- pe-10_obj.c the emergency power shutoff capability is protected from unauthorized activation.

---

## PE-11: Emergency Power
Provide an uninterruptible power supply to facilitate {{ insert: param, pe-11_odp }} in the event of a primary power source loss.

**Guidance:** An uninterruptible power supply (UPS) is an electrical system or mechanism that provides emergency power when there is a failure of the main power source. A UPS is typically used to protect computers, data centers, telecommunication equipment, or other electrical equipment where an unexpected power

**Related:** AT-3, CP-2, CP-7

---

## PE-12: Emergency Lighting
Employ and maintain automatic emergency lighting for the system that activates in the event of a power outage or disruption and that covers emergency exits and evacuation routes within the facility.

**Guidance:** The provision of emergency lighting applies primarily to organizational facilities that contain concentrations of system resources, including data centers, server rooms, and mainframe computer rooms. Emergency lighting provisions for the system are described in the contingency plan for the organizat

**Related:** CP-2, CP-7

**Assessment Objectives:**
- pe-12_obj-1 automatic emergency lighting that activates in the event of a power outage or disruption is employed for the system;
- pe-12_obj-2 automatic emergency lighting that activates in the event of a power outage or disruption is maintained for the system;
- pe-12_obj-3 automatic emergency lighting for the system covers emergency exits within the facility;
- pe-12_obj-4 automatic emergency lighting for the system covers evacuation routes within the facility.

---

## PE-13: Fire Protection
Employ and maintain fire detection and suppression systems that are supported by an independent energy source.

**Guidance:** The provision of fire detection and suppression systems applies primarily to organizational facilities that contain concentrations of system resources, including data centers, server rooms, and mainframe computer rooms. Fire detection and suppression systems that may require an independent energy so

**Related:** AT-3

**Assessment Objectives:**
- pe-13_obj-1 fire detection systems are employed;
- pe-13_obj-2 employed fire detection systems are supported by an independent energy source;
- pe-13_obj-3 employed fire detection systems are maintained;
- pe-13_obj-4 fire suppression systems are employed;
- pe-13_obj-5 employed fire suppression systems are supported by an independent energy source;
- pe-13_obj-6 employed fire suppression systems are maintained.

---

## PE-14: Environmental Controls
(pe-14_smt.a) Maintain {{ insert: param, pe-14_odp.01 }} levels within the facility where the system resides at {{ insert: param, pe-14_odp.03 }} ; and
  (pe-14_smt.b) Monitor environmental control levels {{ insert: param, pe-14_odp.04 }}.

**Guidance:** The provision of environmental controls applies primarily to organizational facilities that contain concentrations of system resources (e.g., data centers, mainframe computer rooms, and server rooms). Insufficient environmental controls, especially in very harsh environments, can have a significant

**Related:** AT-3, CP-2

**Assessment Objectives:**
- pe-14_obj.a {{ insert: param, pe-14_odp.01 }} levels are maintained at {{ insert: param, pe-14_odp.03 }} within the facility where the system resides;
- pe-14_obj.b environmental control levels are monitored {{ insert: param, pe-14_odp.04 }}.

---

## PE-15: Water Damage Protection
Protect the system from damage resulting from water leakage by providing master shutoff or isolation valves that are accessible, working properly, and known to key personnel.

**Guidance:** The provision of water damage protection primarily applies to organizational facilities that contain concentrations of system resources, including data centers, server rooms, and mainframe computer rooms. Isolation valves can be employed in addition to or in lieu of master shutoff valves to shut off

**Related:** AT-3, PE-10

**Assessment Objectives:**
- pe-15_obj-1 the system is protected from damage resulting from water leakage by providing master shutoff or isolation valves;
- pe-15_obj-2 the master shutoff or isolation valves are accessible;
- pe-15_obj-3 the master shutoff or isolation valves are working properly;
- pe-15_obj-4 the master shutoff or isolation valves are known to key personnel.

---

## PE-16: Delivery and Removal
(pe-16_smt.a) Authorize and control {{ insert: param, pe-16_prm_1 }} entering and exiting the facility; and
  (pe-16_smt.b) Maintain records of the system components.

**Guidance:** Enforcing authorizations for entry and exit of system components may require restricting access to delivery areas and isolating the areas from the system and media libraries.

**Related:** CM-3, CM-8, MA-2, MA-3, MP-5, PE-20, SR-2, SR-3, SR-4, SR-6

**Assessment Objectives:**
- pe-16_obj.a
- pe-16_obj.b records of the system components are maintained.

---

## PE-17: Alternate Work Site
(pe-17_smt.a) Determine and document the {{ insert: param, pe-17_odp.01 }} allowed for use by employees;
  (pe-17_smt.b) Employ the following controls at alternate work sites: {{ insert: param, pe-17_odp.02 }};
  (pe-17_smt.c) Assess the effectiveness of controls at alternate work sites; and
  (pe-17_smt.d) Provide a means for employees to communicate with information security and privacy personnel in case of incidents.

**Guidance:** Alternate work sites include government facilities or the private residences of employees. While distinct from alternative processing sites, alternate work sites can provide readily available alternate locations during contingency operations. Organizations can define different sets of controls for s

**Related:** AC-17, AC-18, CP-7

**Assessment Objectives:**
- pe-17_obj.a {{ insert: param, pe-17_odp.01 }} are determined and documented;
- pe-17_obj.b {{ insert: param, pe-17_odp.02 }} are employed at alternate work sites;
- pe-17_obj.c the effectiveness of controls at alternate work sites is assessed;
- pe-17_obj.d a means for employees to communicate with information security and privacy personnel in case of incidents is provided.

---

## PE-18: Location of System Components
Position system components within the facility to minimize potential damage from {{ insert: param, pe-18_odp }} and to minimize the opportunity for unauthorized access.

**Guidance:** Physical and environmental hazards include floods, fires, tornadoes, earthquakes, hurricanes, terrorism, vandalism, an electromagnetic pulse, electrical interference, and other forms of incoming electromagnetic radiation. Organizations consider the location of entry points where unauthorized individ

**Related:** CP-2, PE-5, PE-19, PE-20, RA-3

---

## PE-19: Information Leakage
Protect the system from information leakage due to electromagnetic signals emanations.

**Guidance:** Information leakage is the intentional or unintentional release of data or information to an untrusted environment from electromagnetic signals emanations. The security categories or classifications of systems (with respect to confidentiality), organizational security policies, and risk tolerance gu

**Related:** AC-18, PE-18, PE-20

---

## PE-20: Asset Monitoring and Tracking
Employ {{ insert: param, pe-20_odp.01 }} to track and monitor the location and movement of {{ insert: param, pe-20_odp.02 }} within {{ insert: param, pe-20_odp.03 }}.

**Guidance:** Asset location technologies can help ensure that critical assets—including vehicles, equipment, and system components—remain in authorized locations. Organizations consult with the Office of the General Counsel and senior agency official for privacy regarding the deployment and use of asset location

**Related:** CM-8, PE-16, PM-8

---

## PE-21: Electromagnetic Pulse Protection
Employ {{ insert: param, pe-21_odp.01 }} against electromagnetic pulse damage for {{ insert: param, pe-21_odp.02 }}.

**Guidance:** An electromagnetic pulse (EMP) is a short burst of electromagnetic energy that is spread over a range of frequencies. Such energy bursts may be natural or man-made. EMP interference may be disruptive or damaging to electronic equipment. Protective measures used to mitigate EMP risk include shielding

**Related:** PE-18, PE-19

---

## PE-22: Component Marking
Mark {{ insert: param, pe-22_odp }} indicating the impact level or classification level of the information permitted to be processed, stored, or transmitted by the hardware component.

**Guidance:** Hardware components that may require marking include input and output devices. Input devices include desktop and notebook computers, keyboards, tablets, and smart phones. Output devices include printers, monitors/video displays, facsimile machines, scanners, copiers, and audio devices. Permissions c

**Related:** AC-3, AC-4, AC-16, MP-3

---

## PE-23: Facility Location
(pe-23_smt.a) Plan the location or site of the facility where the system resides considering physical and environmental hazards; and
  (pe-23_smt.b) For existing facilities, consider the physical and environmental hazards in the organizational risk management strategy.

**Guidance:** Physical and environmental hazards include floods, fires, tornadoes, earthquakes, hurricanes, terrorism, vandalism, an electromagnetic pulse, electrical interference, and other forms of incoming electromagnetic radiation. The location of system components within the facility is addressed in [PE-18](

**Related:** CP-2, PE-18, PE-19, PM-8, PM-9, RA-3

**Assessment Objectives:**
- pe-23_obj.a the location or site of the facility where the system resides is planned considering physical and environmental hazards;
- pe-23_obj.b for existing facilities, physical and environmental hazards are considered in the organizational risk management strategy.
