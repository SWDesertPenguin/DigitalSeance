# NIST 800-53: SC — System and Communications Protection

## SC-1: Policy and Procedures
(sc-1_smt.a) Develop, document, and disseminate to {{ insert: param, sc-1_prm_1 }}:
    (sc-1_smt.a.1) {{ insert: param, sc-01_odp.03 }} system and communications protection policy that:
      (sc-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (sc-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (sc-1

**Guidance:** System and communications protection policy and procedures address the controls in the SC family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and

**Related:** PM-9, PS-8, SA-8, SI-12

**Assessment Objectives:**
- sc-1_obj.a
- sc-1_obj.b the {{ insert: param, sc-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the system and communications protection policy and procedures;
- sc-1_obj.c

---

## SC-2: Separation of System and User Functionality
Separate user functionality, including user interface services, from system management functionality.

**Guidance:** System management functionality includes functions that are necessary to administer databases, network components, workstations, or servers. These functions typically require privileged user access. The separation of user functions from system management functions is physical or logical. Organizatio

**Related:** AC-6, SA-4, SA-8, SC-3, SC-7, SC-22, SC-32, SC-39

---

## SC-3: Security Function Isolation
Isolate security functions from nonsecurity functions.

**Guidance:** Security functions are isolated from nonsecurity functions by means of an isolation boundary implemented within a system via partitions and domains. The isolation boundary controls access to and protects the integrity of the hardware, software, and firmware that perform system security functions. Sy

**Related:** AC-3, AC-6, AC-25, CM-2, CM-4, SA-4, SA-5, SA-8, SA-15, SA-17, SC-2, SC-7, SC-32, SC-39, SI-16

---

## SC-4: Information in Shared System Resources
Prevent unauthorized and unintended information transfer via shared system resources.

**Guidance:** Preventing unauthorized and unintended information transfer via shared system resources stops information produced by the actions of prior users or roles (or the actions of processes acting on behalf of prior users or roles) from being available to current users or roles (or current processes acting

**Related:** AC-3, AC-4, SA-8

**Assessment Objectives:**
- sc-4_obj-1 unauthorized information transfer via shared system resources is prevented;
- sc-4_obj-2 unintended information transfer via shared system resources is prevented.

---

## SC-5: Denial-of-service Protection
(sc-5_smt.a) {{ insert: param, sc-05_odp.02 }} the effects of the following types of denial-of-service events: {{ insert: param, sc-05_odp.01 }} ; and
  (sc-5_smt.b) Employ the following controls to achieve the denial-of-service objective: {{ insert: param, sc-05_odp.03 }}.

**Guidance:** Denial-of-service events may occur due to a variety of internal and external causes, such as an attack by an adversary or a lack of planning to support organizational needs with respect to capacity and bandwidth. Such attacks can occur across a wide range of network protocols (e.g., IPv4, IPv6). A v

**Related:** CP-2, IR-4, SC-6, SC-7, SC-40

**Assessment Objectives:**
- sc-5_obj.a the effects of {{ insert: param, sc-05_odp.01 }} are {{ insert: param, sc-05_odp.02 }};
- sc-5_obj.b {{ insert: param, sc-05_odp.03 }} are employed to achieve the denial-of-service protection objective.

---

## SC-6: Resource Availability
Protect the availability of resources by allocating {{ insert: param, sc-06_odp.01 }} by {{ insert: param, sc-06_odp.02 }}.

**Guidance:** Priority protection prevents lower-priority processes from delaying or interfering with the system that services higher-priority processes. Quotas prevent users or processes from obtaining more than predetermined amounts of resources.

**Related:** SC-5

---

## SC-7: Boundary Protection
(sc-7_smt.a) Monitor and control communications at the external managed interfaces to the system and at key internal managed interfaces within the system;
  (sc-7_smt.b) Implement subnetworks for publicly accessible system components that are {{ insert: param, sc-07_odp }} separated from internal organizational networks; and
  (sc-7_smt.c) Connect to external networks or systems only through managed interfaces consisting of boundary protection devices arranged in accordance with an organizationa

**Guidance:** Managed interfaces include gateways, routers, firewalls, guards, network-based malicious code analysis, virtualization systems, or encrypted tunnels implemented within a security architecture. Subnetworks that are physically or logically separated from internal networks are referred to as demilitari

**Related:** AC-4, AC-17, AC-18, AC-19, AC-20, AU-13, CA-3, CM-2, CM-4, CM-7, CM-10, CP-8, CP-10, IR-4, MA-4, PE-3, PL-8, PM-12, SA-8, SA-17, SC-5, SC-26, SC-32, SC-35, SC-43

**Assessment Objectives:**
- sc-7_obj.a
- sc-7_obj.b subnetworks for publicly accessible system components are {{ insert: param, sc-07_odp }} separated from internal organizational networks;
- sc-7_obj.c external networks or systems are only connected to through managed interfaces consisting of boundary protection devices arranged in accordance with an organizational security and privacy architecture.

---

## SC-8: Transmission Confidentiality and Integrity
Protect the {{ insert: param, sc-08_odp }} of transmitted information.

**Guidance:** Protecting the confidentiality and integrity of transmitted information applies to internal and external networks as well as any system components that can transmit information, including servers, notebook computers, desktop computers, mobile devices, printers, copiers, scanners, facsimile machines,

**Related:** AC-17, AC-18, AU-10, IA-3, IA-8, IA-9, MA-4, PE-4, SA-4, SA-8, SC-7, SC-16, SC-20, SC-23, SC-28

---

## SC-10: Network Disconnect
Terminate the network connection associated with a communications session at the end of the session or after {{ insert: param, sc-10_odp }} of inactivity.

**Guidance:** Network disconnect applies to internal and external networks. Terminating network connections associated with specific communications sessions includes de-allocating TCP/IP address or port pairs at the operating system level and de-allocating the networking assignments at the application level if mu

**Related:** AC-17, SC-23

---

## SC-11: Trusted Path
(sc-11_smt.a) Provide a {{ insert: param, sc-11_odp.01 }} isolated trusted communications path for communications between the user and the trusted components of the system; and
  (sc-11_smt.b) Permit users to invoke the trusted communications path for communications between the user and the following security functions of the system, including at a minimum, authentication and re-authentication: {{ insert: param, sc-11_odp.02 }}.

**Guidance:** Trusted paths are mechanisms by which users can communicate (using input devices such as keyboards) directly with the security functions of systems with the requisite assurance to support security policies. Trusted path mechanisms can only be activated by users or the security functions of organizat

**Related:** AC-16, AC-25, SC-12, SC-23

**Assessment Objectives:**
- sc-11_obj.a a {{ insert: param, sc-11_odp.01 }} isolated trusted communication path is provided for communications between the user and the trusted components of the system;
- sc-11_obj.b users are permitted to invoke the trusted communication path for communications between the user and the {{ insert: param, sc-11_odp.02 }} of the system, including authentication and re-authentication, at a minimum.

---

## SC-12: Cryptographic Key Establishment and Management
Establish and manage cryptographic keys when cryptography is employed within the system in accordance with the following key management requirements: {{ insert: param, sc-12_odp }}.

**Guidance:** Cryptographic key management and establishment can be performed using manual procedures or automated mechanisms with supporting manual procedures. Organizations define key management requirements in accordance with applicable laws, executive orders, directives, regulations, policies, standards, and

**Related:** AC-17, AU-9, AU-10, CM-3, IA-3, IA-7, IA-13, SA-4, SA-8, SA-9, SC-8, SC-11, SC-13, SC-17, SC-20, SC-37, SC-40, SI-3, SI-7

**Assessment Objectives:**
- sc-12_obj-1 cryptographic keys are established when cryptography is employed within the system in accordance with {{ insert: param, sc-12_odp }};
- sc-12_obj-2 cryptographic keys are managed when cryptography is employed within the system in accordance with {{ insert: param, sc-12_odp }}.

---

## SC-13: Cryptographic Protection
(sc-13_smt.a) Determine the {{ insert: param, sc-13_odp.01 }} ; and
  (sc-13_smt.b) Implement the following types of cryptography required for each specified cryptographic use: {{ insert: param, sc-13_odp.02 }}.

**Guidance:** Cryptography can be employed to support a variety of security solutions, including the protection of classified information and controlled unclassified information, the provision and implementation of digital signatures, and the enforcement of information separation when authorized individuals have

**Related:** AC-2, AC-3, AC-7, AC-17, AC-18, AC-19, AU-9, AU-10, CM-11, CP-9, IA-3, IA-5, IA-7, IA-13, MA-4, MP-2, MP-4, MP-5, SA-4, SA-8, SA-9, SC-8, SC-12, SC-20, SC-23, SC-28, SC-40, SI-3, SI-7

**Assessment Objectives:**
- sc-13_obj.a {{ insert: param, sc-13_odp.01 }} are identified;
- sc-13_obj.b {{ insert: param, sc-13_odp.02 }} for each specified cryptographic use (defined in SC-13_ODP[01]) are implemented.

---

## SC-15: Collaborative Computing Devices and Applications
(sc-15_smt.a) Prohibit remote activation of collaborative computing devices and applications with the following exceptions: {{ insert: param, sc-15_odp }} ; and
  (sc-15_smt.b) Provide an explicit indication of use to users physically present at the devices.

**Guidance:** Collaborative computing devices and applications include remote meeting devices and applications, networked white boards, cameras, and microphones. The explicit indication of use includes signals to users when collaborative computing devices and applications are activated.

**Related:** AC-21, SC-42

**Assessment Objectives:**
- sc-15_obj.a remote activation of collaborative computing devices and applications is prohibited except {{ insert: param, sc-15_odp }};
- sc-15_obj.b an explicit indication of use is provided to users physically present at the devices.

---

## SC-16: Transmission of Security and Privacy Attributes
Associate {{ insert: param, sc-16_prm_1 }} with information exchanged between systems and between system components.

**Guidance:** Security and privacy attributes can be explicitly or implicitly associated with the information contained in organizational systems or system components. Attributes are abstractions that represent the basic properties or characteristics of an entity with respect to protecting information or the mana

**Related:** AC-3, AC-4, AC-16

**Assessment Objectives:**
- sc-16_obj-1 {{ insert: param, sc-16_odp.01 }} are associated with information exchanged between systems;
- sc-16_obj-2 {{ insert: param, sc-16_odp.01 }} are associated with information exchanged between system components;
- sc-16_obj-3 {{ insert: param, sc-16_odp.02 }} are associated with information exchanged between systems;
- sc-16_obj-4 {{ insert: param, sc-16_odp.02 }} are associated with information exchanged between system components.

---

## SC-17: Public Key Infrastructure Certificates
(sc-17_smt.a) Issue public key certificates under an {{ insert: param, sc-17_odp }} or obtain public key certificates from an approved service provider; and
  (sc-17_smt.b) Include only approved trust anchors in trust stores or certificate stores managed by the organization.

**Guidance:** Public key infrastructure (PKI) certificates are certificates with visibility external to organizational systems and certificates related to the internal operations of systems, such as application-specific time services. In cryptographic systems with a hierarchical structure, a trust anchor is an au

**Related:** AU-10, IA-5, SC-12

**Assessment Objectives:**
- sc-17_obj.a public key certificates are issued under {{ insert: param, sc-17_odp }} , or public key certificates are obtained from an approved service provider;
- sc-17_obj.b only approved trust anchors are included in trust stores or certificate stores managed by the organization.

---

## SC-18: Mobile Code
(sc-18_smt.a) Define acceptable and unacceptable mobile code and mobile code technologies; and
  (sc-18_smt.b) Authorize, monitor, and control the use of mobile code within the system.

**Guidance:** Mobile code includes any program, application, or content that can be transmitted across a network (e.g., embedded in an email, document, or website) and executed on a remote system. Decisions regarding the use of mobile code within organizational systems are based on the potential for the code to c

**Related:** AU-2, AU-12, CM-2, CM-6, SI-3

**Assessment Objectives:**
- sc-18_obj.a
- sc-18_obj.b

---

## SC-20: Secure Name/Address Resolution Service (Authoritative Source)
(sc-20_smt.a) Provide additional data origin authentication and integrity verification artifacts along with the authoritative name resolution data the system returns in response to external name/address resolution queries; and
  (sc-20_smt.b) Provide the means to indicate the security status of child zones and (if the child supports secure resolution services) to enable verification of a chain of trust among parent and child domains, when operating as part of a distributed, hierarchical namespac

**Guidance:** Providing authoritative source information enables external clients, including remote Internet clients, to obtain origin authentication and integrity verification assurances for the host/service name to network address resolution information obtained through the service. Systems that provide name an

**Related:** AU-10, SC-8, SC-12, SC-13, SC-21, SC-22

**Assessment Objectives:**
- sc-20_obj.a
- sc-20_obj.b

---

## SC-21: Secure Name/Address Resolution Service (Recursive or Caching Resolver)
Request and perform data origin authentication and data integrity verification on the name/address resolution responses the system receives from authoritative sources.

**Guidance:** Each client of name resolution services either performs this validation on its own or has authenticated channels to trusted validation providers. Systems that provide name and address resolution services for local clients include recursive resolving or caching domain name system (DNS) servers. DNS c

**Related:** SC-20, SC-22

**Assessment Objectives:**
- sc-21_obj-1 data origin authentication is requested for the name/address resolution responses that the system receives from authoritative sources;
- sc-21_obj-2 data origin authentication is performed on the name/address resolution responses that the system receives from authoritative sources;
- sc-21_obj-3 data integrity verification is requested for the name/address resolution responses that the system receives from authoritative sources;
- sc-21_obj-4 data integrity verification is performed on the name/address resolution responses that the system receives from authoritative sources.

---

## SC-22: Architecture and Provisioning for Name/Address Resolution Service
Ensure the systems that collectively provide name/address resolution service for an organization are fault-tolerant and implement internal and external role separation.

**Guidance:** Systems that provide name and address resolution services include domain name system (DNS) servers. To eliminate single points of failure in systems and enhance redundancy, organizations employ at least two authoritative domain name system servers—one configured as the primary server and the other c

**Related:** SC-2, SC-20, SC-21, SC-24

**Assessment Objectives:**
- sc-22_obj-1 the systems that collectively provide name/address resolution services for an organization are fault-tolerant;
- sc-22_obj-2 the systems that collectively provide name/address resolution services for an organization implement internal role separation;
- sc-22_obj-3 the systems that collectively provide name/address resolution services for an organization implement external role separation.

---

## SC-23: Session Authenticity
Protect the authenticity of communications sessions.

**Guidance:** Protecting session authenticity addresses communications protection at the session level, not at the packet level. Such protection establishes grounds for confidence at both ends of communications sessions in the ongoing identities of other parties and the validity of transmitted information. Authen

**Related:** AU-10, SC-8, SC-10, SC-11

---

## SC-24: Fail in Known State
Fail to a {{ insert: param, sc-24_odp.02 }} for the following failures on the indicated components while preserving {{ insert: param, sc-24_odp.03 }} in failure: {{ insert: param, sc-24_odp.01 }}.

**Guidance:** Failure in a known state addresses security concerns in accordance with the mission and business needs of organizations. Failure in a known state prevents the loss of confidentiality, integrity, or availability of information in the event of failures of organizational systems or system components. F

**Related:** CP-2, CP-4, CP-10, CP-12, SA-8, SC-7, SC-22, SI-13

---

## SC-25: Thin Nodes
Employ minimal functionality and information storage on the following system components: {{ insert: param, sc-25_odp }}.

**Guidance:** The deployment of system components with minimal functionality reduces the need to secure every endpoint and may reduce the exposure of information, systems, and services to attacks. Reduced or minimal functionality includes diskless nodes and thin client technologies.

**Related:** SC-30, SC-44

**Assessment Objectives:**
- sc-25_obj-1 minimal functionality for {{ insert: param, sc-25_odp }} is employed;
- sc-25_obj-2 minimal information storage on {{ insert: param, sc-25_odp }} is allocated.

---

## SC-26: Decoys
Include components within organizational systems specifically designed to be the target of malicious attacks for detecting, deflecting, and analyzing such attacks.

**Guidance:** Decoys (i.e., honeypots, honeynets, or deception nets) are established to attract adversaries and deflect attacks away from the operational systems that support organizational mission and business functions. Use of decoys requires some supporting isolation measures to ensure that any deflected malic

**Related:** RA-5, SC-7, SC-30, SC-35, SC-44, SI-3, SI-4

**Assessment Objectives:**
- sc-26_obj-1 components within organizational systems specifically designed to be the target of malicious attacks are included to detect such attacks;
- sc-26_obj-2 components within organizational systems specifically designed to be the target of malicious attacks are included to deflect such attacks;
- sc-26_obj-3 components within organizational systems specifically designed to be the target of malicious attacks are included to analyze such attacks.

---

## SC-27: Platform-independent Applications
Include within organizational systems the following platform independent applications: {{ insert: param, sc-27_odp }}.

**Guidance:** Platforms are combinations of hardware, firmware, and software components used to execute software applications. Platforms include operating systems, the underlying computer architectures, or both. Platform-independent applications are applications with the capability to execute on multiple platform

**Related:** SC-29

---

## SC-28: Protection of Information at Rest
Protect the {{ insert: param, sc-28_odp.01 }} of the following information at rest: {{ insert: param, sc-28_odp.02 }}.

**Guidance:** Information at rest refers to the state of information when it is not in process or in transit and is located on system components. Such components include internal or external hard disk drives, storage area network devices, or databases. However, the focus of protecting information at rest is not o

**Related:** AC-3, AC-4, AC-6, AC-19, CA-7, CM-3, CM-5, CM-6, CP-9, MP-4, MP-5, PE-3, SC-8, SC-12, SC-13, SC-34, SI-3, SI-7, SI-16

---

## SC-29: Heterogeneity
Employ a diverse set of information technologies for the following system components in the implementation of the system: {{ insert: param, sc-29_odp }}.

**Guidance:** Increasing the diversity of information technologies within organizational systems reduces the impact of potential exploitations or compromises of specific technologies. Such diversity protects against common mode failures, including those failures induced by supply chain attacks. Diversity in infor

**Related:** AU-9, PL-8, SC-27, SC-30, SR-3

---

## SC-30: Concealment and Misdirection
Employ the following concealment and misdirection techniques for {{ insert: param, sc-30_odp.02 }} at {{ insert: param, sc-30_odp.03 }} to confuse and mislead adversaries: {{ insert: param, sc-30_odp.01 }}.

**Guidance:** Concealment and misdirection techniques can significantly reduce the targeting capabilities of adversaries (i.e., window of opportunity and available attack surface) to initiate and complete attacks. For example, virtualization techniques provide organizations with the ability to disguise systems, p

**Related:** AC-6, SC-25, SC-26, SC-29, SC-44, SI-14

---

## SC-31: Covert Channel Analysis
(sc-31_smt.a) Perform a covert channel analysis to identify those aspects of communications within the system that are potential avenues for covert {{ insert: param, sc-31_odp }} channels; and
  (sc-31_smt.b) Estimate the maximum bandwidth of those channels.

**Guidance:** Developers are in the best position to identify potential areas within systems that might lead to covert channels. Covert channel analysis is a meaningful activity when there is the potential for unauthorized information flows across security domains, such as in the case of systems that contain expo

**Related:** AC-3, AC-4, SA-8, SI-11

**Assessment Objectives:**
- sc-31_obj.a a covert channel analysis is performed to identify those aspects of communications within the system that are potential avenues for covert {{ insert: param, sc-31_odp }} channels;
- sc-31_obj.b the maximum bandwidth of those channels is estimated.

---

## SC-32: System Partitioning
Partition the system into {{ insert: param, sc-32_odp.01 }} residing in separate {{ insert: param, sc-32_odp.02 }} domains or environments based on {{ insert: param, sc-32_odp.03 }}.

**Guidance:** System partitioning is part of a defense-in-depth protection strategy. Organizations determine the degree of physical separation of system components. Physical separation options include physically distinct components in separate racks in the same room, critical components in separate rooms, and geo

**Related:** AC-4, AC-6, SA-8, SC-2, SC-3, SC-7, SC-36

---

## SC-34: Non-modifiable Executable Programs
For {{ insert: param, sc-34_odp.01 }} , load and execute:
  (sc-34_smt.a) The operating environment from hardware-enforced, read-only media; and
  (sc-34_smt.b) The following applications from hardware-enforced, read-only media: {{ insert: param, sc-34_odp.02 }}.

**Guidance:** The operating environment for a system contains the code that hosts applications, including operating systems, executives, or virtual machine monitors (i.e., hypervisors). It can also include certain applications that run directly on hardware platforms. Hardware-enforced, read-only media include Com

**Related:** AC-3, SI-7, SI-14

**Assessment Objectives:**
- sc-34_obj.a the operating environment for {{ insert: param, sc-34_odp.01 }} is loaded and executed from hardware-enforced, read-only media;
- sc-34_obj.b {{ insert: param, sc-34_odp.02 }} for {{ insert: param, sc-34_odp.01 }} are loaded and executed from hardware-enforced, read-only media.

---

## SC-35: External Malicious Code Identification
Include system components that proactively seek to identify network-based malicious code or malicious websites.

**Guidance:** External malicious code identification differs from decoys in [SC-26](#sc-26) in that the components actively probe networks, including the Internet, in search of malicious code contained on external websites. Like decoys, the use of external malicious code identification techniques requires some su

**Related:** SC-7, SC-26, SC-44, SI-3, SI-4

---

## SC-36: Distributed Processing and Storage
Distribute the following processing and storage components across multiple {{ insert: param, sc-36_prm_1 }}: {{ insert: param, sc-36_prm_2 }}.

**Guidance:** Distributing processing and storage across multiple physical locations or logical domains provides a degree of redundancy or overlap for organizations. The redundancy and overlap increase the work factor of adversaries to adversely impact organizational operations, assets, and individuals. The use o

**Related:** CP-6, CP-7, PL-8, SC-32

**Assessment Objectives:**
- sc-36_obj-1 {{ insert: param, sc-36_odp.01 }} are distributed across {{ insert: param, sc-36_odp.02 }};
- sc-36_obj-2 {{ insert: param, sc-36_odp.03 }} are distributed across {{ insert: param, sc-36_odp.04 }}.

---

## SC-37: Out-of-band Channels
Employ the following out-of-band channels for the physical delivery or electronic transmission of {{ insert: param, sc-37_odp.02 }} to {{ insert: param, sc-37_odp.03 }}: {{ insert: param, sc-37_odp.01 }}.

**Guidance:** Out-of-band channels include local, non-network accesses to systems; network paths physically separate from network paths used for operational traffic; or non-electronic paths, such as the U.S. Postal Service. The use of out-of-band channels is contrasted with the use of in-band channels (i.e., the

**Related:** AC-2, CM-3, CM-5, CM-7, IA-2, IA-4, IA-5, MA-4, SC-12, SI-3, SI-4, SI-7

---

## SC-38: Operations Security
Employ the following operations security controls to protect key organizational information throughout the system development life cycle: {{ insert: param, sc-38_odp }}.

**Guidance:** Operations security (OPSEC) is a systematic process by which potential adversaries can be denied information about the capabilities and intentions of organizations by identifying, controlling, and protecting generally unclassified information that specifically relates to the planning and execution o

**Related:** CA-2, CA-7, PL-1, PM-9, PM-12, RA-2, RA-3, RA-5, SC-7, SR-3, SR-7

---

## SC-39: Process Isolation
Maintain a separate execution domain for each executing system process.

**Guidance:** Systems can maintain separate execution domains for each executing process by assigning each process a separate address space. Each system process has a distinct address space so that communication between processes is performed in a manner controlled through the security functions, and one process

**Related:** AC-3, AC-4, AC-6, AC-25, SA-8, SC-2, SC-3, SI-16

---

## SC-40: Wireless Link Protection
Protect external and internal {{ insert: param, sc-40_prm_1 }} from the following signal parameter attacks: {{ insert: param, sc-40_prm_2 }}.

**Guidance:** Wireless link protection applies to internal and external wireless communication links that may be visible to individuals who are not authorized system users. Adversaries can exploit the signal parameters of wireless links if such links are not adequately protected. There are many ways to exploit th

**Related:** AC-18, SC-5

**Assessment Objectives:**
- sc-40_obj-1 external {{ insert: param, sc-40_odp.01 }} are protected from {{ insert: param, sc-40_odp.02 }}.
- sc-40_obj-2 internal {{ insert: param, sc-40_odp.03 }} are protected from {{ insert: param, sc-40_odp.04 }}.

---

## SC-41: Port and I/O Device Access
{{ insert: param, sc-41_odp.02 }} disable or remove {{ insert: param, sc-41_odp.01 }} on the following systems or system components: {{ insert: param, sc-41_odp.03 }}.

**Guidance:** Connection ports include Universal Serial Bus (USB), Thunderbolt, and Firewire (IEEE 1394). Input/output (I/O) devices include compact disc and digital versatile disc drives. Disabling or removing such connection ports and I/O devices helps prevent the exfiltration of information from systems and th

**Related:** AC-20, MP-7

---

## SC-42: Sensor Capability and Data
(sc-42_smt.a) Prohibit {{ insert: param, sc-42_odp.01 }} ; and
  (sc-42_smt.b) Provide an explicit indication of sensor use to {{ insert: param, sc-42_odp.05 }}.

**Guidance:** Sensor capability and data applies to types of systems or system components characterized as mobile devices, such as cellular telephones, smart phones, and tablets. Mobile devices often include sensors that can collect and record data regarding the environment where the system is in use. Sensors tha

**Related:** SC-15

**Assessment Objectives:**
- sc-42_obj.a {{ insert: param, sc-42_odp.01 }} is/are prohibited;
- sc-42_obj.b an explicit indication of sensor use is provided to {{ insert: param, sc-42_odp.05 }}.

---

## SC-43: Usage Restrictions
(sc-43_smt.a) Establish usage restrictions and implementation guidelines for the following system components: {{ insert: param, sc-43_odp }} ; and
  (sc-43_smt.b) Authorize, monitor, and control the use of such components within the system.

**Guidance:** Usage restrictions apply to all system components including but not limited to mobile code, mobile devices, wireless access, and wired and wireless peripheral components (e.g., copiers, printers, scanners, optical devices, and other similar technologies). The usage restrictions and implementation gu

**Related:** AC-18, AC-19, CM-6, SC-7, SC-18

**Assessment Objectives:**
- sc-43_obj.a usage restrictions and implementation guidelines are established for {{ insert: param, sc-43_odp }};
- sc-43_obj.b

---

## SC-44: Detonation Chambers
Employ a detonation chamber capability within {{ insert: param, sc-44_odp }}.

**Guidance:** Detonation chambers, also known as dynamic execution environments, allow organizations to open email attachments, execute untrusted or suspicious applications, and execute Universal Resource Locator requests in the safety of an isolated environment or a virtualized sandbox. Protected and isolated ex

**Related:** SC-7, SC-18, SC-25, SC-26, SC-30, SC-35, SC-39, SI-3, SI-7

---

## SC-45: System Time Synchronization
Synchronize system clocks within and between systems and system components.

**Guidance:** Time synchronization of system clocks is essential for the correct execution of many system services, including identification and authentication processes that involve certificates and time-of-day restrictions as part of access control. Denial of service or failure to deny expired credentials may r

**Related:** AC-3, AU-8, IA-2, IA-8

---

## SC-46: Cross Domain Policy Enforcement
Implement a policy enforcement mechanism {{ insert: param, sc-46_odp }} between the physical and/or network interfaces for the connecting security domains.

**Guidance:** For logical policy enforcement mechanisms, organizations avoid creating a logical path between interfaces to prevent the ability to bypass the policy enforcement mechanism. For physical policy enforcement mechanisms, the robustness of physical isolation afforded by the physical implementation of pol

**Related:** AC-4, SC-7

---

## SC-47: Alternate Communications Paths
Establish {{ insert: param, sc-47_odp }} for system operations organizational command and control.

**Guidance:** An incident, whether adversarial- or nonadversarial-based, can disrupt established communications paths used for system operations and organizational command and control. Alternate communications paths reduce the risk of all communications paths being affected by the same incident. To compound the p

**Related:** CP-2, CP-8

---

## SC-48: Sensor Relocation
Relocate {{ insert: param, sc-48_odp.01 }} to {{ insert: param, sc-48_odp.02 }} under the following conditions or circumstances: {{ insert: param, sc-48_odp.03 }}.

**Guidance:** Adversaries may take various paths and use different approaches as they move laterally through an organization (including its systems) to reach their target or as they attempt to exfiltrate information from the organization. The organization often only has a limited set of monitoring and detection c

**Related:** AU-2, SC-7, SI-4

---

## SC-49: Hardware-enforced Separation and Policy Enforcement
Implement hardware-enforced separation and policy enforcement mechanisms between {{ insert: param, sc-49_odp }}.

**Guidance:** System owners may require additional strength of mechanism and robustness to ensure domain separation and policy enforcement for specific types of threats and environments of operation. Hardware-enforced separation and policy enforcement provide greater strength of mechanism than software-enforced s

**Related:** AC-4, SA-8, SC-50

---

## SC-50: Software-enforced Separation and Policy Enforcement
Implement software-enforced separation and policy enforcement mechanisms between {{ insert: param, sc-50_odp }}.

**Guidance:** System owners may require additional strength of mechanism to ensure domain separation and policy enforcement for specific types of threats and environments of operation.

**Related:** AC-3, AC-4, SA-8, SC-2, SC-3, SC-49

---

## SC-51: Hardware-based Protection
(sc-51_smt.a) Employ hardware-based, write-protect for {{ insert: param, sc-51_odp.01 }} ; and
  (sc-51_smt.b) Implement specific procedures for {{ insert: param, sc-51_odp.02 }} to manually disable hardware write-protect for firmware modifications and re-enable the write-protect prior to returning to operational mode.

**Guidance:** None.

**Assessment Objectives:**
- sc-51_obj.a hardware-based write-protect for {{ insert: param, sc-51_odp.01 }} is employed;
- sc-51_obj.b
