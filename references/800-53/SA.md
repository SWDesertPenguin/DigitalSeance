# NIST 800-53: SA — System and Services Acquisition

## SA-1: Policy and Procedures
(sa-1_smt.a) Develop, document, and disseminate to {{ insert: param, sa-1_prm_1 }}:
    (sa-1_smt.a.1) {{ insert: param, sa-01_odp.03 }} system and services acquisition policy that:
      (sa-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (sa-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (sa-1_smt.

**Guidance:** System and services acquisition policy and procedures address the controls in the SA family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and priv

**Related:** PM-9, PS-8, SA-8, SI-12

**Assessment Objectives:**
- sa-1_obj.a
- sa-1_obj.b the {{ insert: param, sa-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the system and services acquisition policy and procedures;
- sa-1_obj.c

---

## SA-2: Allocation of Resources
(sa-2_smt.a) Determine the high-level information security and privacy requirements for the system or system service in mission and business process planning;
  (sa-2_smt.b) Determine, document, and allocate the resources required to protect the system or system service as part of the organizational capital planning and investment control process; and
  (sa-2_smt.c) Establish a discrete line item for information security and privacy in organizational programming and budgeting documentation.

**Guidance:** Resource allocation for information security and privacy includes funding for system and services acquisition, sustainment, and supply chain-related risks throughout the system development life cycle.

**Related:** PL-7, PM-3, PM-11, SA-9, SR-3, SR-5

**Assessment Objectives:**
- sa-2_obj.a
- sa-2_obj.b
- sa-2_obj.c

---

## SA-3: System Development Life Cycle
(sa-3_smt.a) Acquire, develop, and manage the system using {{ insert: param, sa-03_odp }} that incorporates information security and privacy considerations;
  (sa-3_smt.b) Define and document information security and privacy roles and responsibilities throughout the system development life cycle;
  (sa-3_smt.c) Identify individuals having information security and privacy roles and responsibilities; and
  (sa-3_smt.d) Integrate the organizational information security and privacy risk management p

**Guidance:** A system development life cycle process provides the foundation for the successful development, implementation, and operation of organizational systems. The integration of security and privacy considerations early in the system development life cycle is a foundational principle of systems security e

**Related:** AT-3, PL-8, PM-7, SA-4, SA-5, SA-8, SA-11, SA-15, SA-17, SA-22, SR-3, SR-4, SR-5, SR-9

**Assessment Objectives:**
- sa-3_obj.a
- sa-3_obj.b
- sa-3_obj.c
- sa-3_obj.d

---

## SA-4: Acquisition Process
Include the following requirements, descriptions, and criteria, explicitly or by reference, using {{ insert: param, sa-04_odp.01 }} in the acquisition contract for the system, system component, or system service:
  (sa-4_smt.a) Security and privacy functional requirements;
  (sa-4_smt.b) Strength of mechanism requirements;
  (sa-4_smt.c) Security and privacy assurance requirements;
  (sa-4_smt.d) Controls needed to satisfy the security and privacy requirements.
  (sa-4_smt.e) Security and privac

**Guidance:** Security and privacy functional requirements are typically derived from the high-level security and privacy requirements described in [SA-2](#sa-2) . The derived requirements include security and privacy capabilities, functions, and mechanisms. Strength requirements associated with such capabilities

**Related:** CM-6, CM-8, PS-7, SA-3, SA-5, SA-8, SA-11, SA-15, SA-16, SA-17, SA-21, SR-3, SR-5

**Assessment Objectives:**
- sa-4_obj.a
- sa-4_obj.b strength of mechanism requirements, descriptions, and criteria are included explicitly or by reference using {{ insert: param, sa-04_odp.01 }} in the acquisition contract for the system, system component, or system service;
- sa-4_obj.c
- sa-4_obj.d
- sa-4_obj.e
- sa-4_obj.f
- sa-4_obj.g the description of the system development environment and environment in which the system is intended to operate, requirements, and criteria are included explicitly or by reference using {{ insert: param, sa-04_odp.01 }} in the acquisition contract for the system, system component, or system service;
- sa-4_obj.h
- sa-4_obj.i acceptance criteria requirements and descriptions are included explicitly or by reference using {{ insert: param, sa-04_odp.01 }} in the acquisition contract for the system, system component, or system service.

---

## SA-5: System Documentation
(sa-5_smt.a) Obtain or develop administrator documentation for the system, system component, or system service that describes:
    (sa-5_smt.a.1) Secure configuration, installation, and operation of the system, component, or service;
    (sa-5_smt.a.2) Effective use and maintenance of security and privacy functions and mechanisms; and
    (sa-5_smt.a.3) Known vulnerabilities regarding configuration and use of administrative or privileged functions;
  (sa-5_smt.b) Obtain or develop user documenta

**Guidance:** System artifacts and documentation created by the developer helps organizational personnel understand the implementation and operation of controls. Organizations consider establishing specific measures to determine the quality and completeness of the content provided. System documentation may be use

**Related:** CM-4, CM-6, CM-7, CM-8, PL-2, PL-4, PL-8, PS-2, SA-3, SA-4, SA-8, SA-9, SA-10, SA-11, SA-15, SA-16, SA-17, SI-12, SR-3

**Assessment Objectives:**
- sa-5_obj.a
- sa-5_obj.b
- sa-5_obj.c
- sa-5_obj.d documentation is distributed to {{ insert: param, sa-05_odp.02 }}.

---

## SA-8: Security and Privacy Engineering Principles
Apply the following systems security and privacy engineering principles in the specification, design, development, implementation, and modification of the system and system components: {{ insert: param, sa-8_prm_1 }}.

**Guidance:** Systems security and privacy engineering principles are closely related to and implemented throughout the system development life cycle (see [SA-3](#sa-3) ). Organizations can apply systems security and privacy engineering principles to new systems under development or to systems undergoing upgrades

**Related:** PL-8, PM-7, RA-2, RA-3, RA-9, SA-3, SA-4, SA-15, SA-17, SA-20, SC-2, SC-3, SC-32, SC-39, SR-2, SR-3, SR-4, SR-5

**Assessment Objectives:**
- sa-8_obj-1 {{ insert: param, sa-08_odp.01 }} are applied in the specification of the system and system components;
- sa-8_obj-2 {{ insert: param, sa-08_odp.01 }} are applied in the design of the system and system components;
- sa-8_obj-3 {{ insert: param, sa-08_odp.01 }} are applied in the development of the system and system components;
- sa-8_obj-4 {{ insert: param, sa-08_odp.01 }} are applied in the implementation of the system and system components;
- sa-8_obj-5 {{ insert: param, sa-08_odp.01 }} are applied in the modification of the system and system components;
- sa-8_obj-6 {{ insert: param, sa-08_odp.02 }} are applied in the specification of the system and system components;
- sa-8_obj-7 {{ insert: param, sa-08_odp.02 }} are applied in the design of the system and system components;
- sa-8_obj-8 {{ insert: param, sa-08_odp.02 }} are applied in the development of the system and system components;
- sa-8_obj-9 {{ insert: param, sa-08_odp.02 }} are applied in the implementation of the system and system components;
- sa-8_obj-10 {{ insert: param, sa-08_odp.02 }} are applied in the modification of the system and system components.

---

## SA-9: External System Services
(sa-9_smt.a) Require that providers of external system services comply with organizational security and privacy requirements and employ the following controls: {{ insert: param, sa-09_odp.01 }};
  (sa-9_smt.b) Define and document organizational oversight and user roles and responsibilities with regard to external system services; and
  (sa-9_smt.c) Employ the following processes, methods, and techniques to monitor control compliance by external service providers on an ongoing basis: {{ insert: p

**Guidance:** External system services are provided by an external provider, and the organization has no direct control over the implementation of the required controls or the assessment of control effectiveness. Organizations establish relationships with external service providers in a variety of ways, including

**Related:** AC-20, CA-3, CP-2, IR-4, IR-7, PL-10, PL-11, PS-7, SA-2, SA-4, SR-3, SR-5

**Assessment Objectives:**
- sa-9_obj.a
- sa-9_obj.b
- sa-9_obj.c {{ insert: param, sa-09_odp.02 }} are employed to monitor control compliance by external service providers on an ongoing basis.

---

## SA-10: Developer Configuration Management
Require the developer of the system, system component, or system service to:
  (sa-10_smt.a) Perform configuration management during system, component, or service {{ insert: param, sa-10_odp.01 }};
  (sa-10_smt.b) Document, manage, and control the integrity of changes to {{ insert: param, sa-10_odp.02 }};
  (sa-10_smt.c) Implement only organization-approved changes to the system, component, or service;
  (sa-10_smt.d) Document approved changes to the system, component, or service and the potenti

**Guidance:** Organizations consider the quality and completeness of configuration management activities conducted by developers as direct evidence of applying effective security controls. Controls include protecting the master copies of material used to generate security-relevant portions of the system hardware,

**Related:** CM-2, CM-3, CM-4, CM-7, CM-9, SA-4, SA-5, SA-8, SA-15, SI-2, SR-3, SR-4, SR-5, SR-6

**Assessment Objectives:**
- sa-10_obj.a the developer of the system, system component, or system service is required to perform configuration management during system, component, or service {{ insert: param, sa-10_odp.01 }};
- sa-10_obj.b
- sa-10_obj.c the developer of the system, system component, or system service is required to implement only organization-approved changes to the system, component, or service;
- sa-10_obj.d
- sa-10_obj.e

---

## SA-11: Developer Testing and Evaluation
Require the developer of the system, system component, or system service, at all post-design stages of the system development life cycle, to:
  (sa-11_smt.a) Develop and implement a plan for ongoing security and privacy control assessments;
  (sa-11_smt.b) Perform {{ insert: param, sa-11_odp.01 }} testing/evaluation {{ insert: param, sa-11_odp.02 }} at {{ insert: param, sa-11_odp.03 }};
  (sa-11_smt.c) Produce evidence of the execution of the assessment plan and the results of the testing and ev

**Guidance:** Developmental testing and evaluation confirms that the required controls are implemented correctly, operating as intended, enforcing the desired security and privacy policies, and meeting established security and privacy requirements. Security properties of systems and the privacy of individuals may

**Related:** CA-2, CA-7, CM-4, SA-3, SA-4, SA-5, SA-8, SA-15, SA-17, SI-2, SR-5, SR-6, SR-7

**Assessment Objectives:**
- sa-11_obj.a
- sa-11_obj.b the developer of the system, system component, or system service is required at all post-design stages of the system development life cycle to perform {{ insert: param, sa-11_odp.01 }} testing/evaluation {{ insert: param, sa-11_odp.02 }} at {{ insert: param, sa-11_odp.03 }};
- sa-11_obj.c
- sa-11_obj.d the developer of the system, system component, or system service is required at all post-design stages of the system development life cycle to implement a verifiable flaw remediation process;
- sa-11_obj.e the developer of the system, system component, or system service is required at all post-design stages of the system development life cycle to correct flaws identified during testing and evaluation.

---

## SA-15: Development Process, Standards, and Tools
(sa-15_smt.a) Require the developer of the system, system component, or system service to follow a documented development process that:
    (sa-15_smt.a.1) Explicitly addresses security and privacy requirements;
    (sa-15_smt.a.2) Identifies the standards and tools used in the development process;
    (sa-15_smt.a.3) Documents the specific tool options and tool configurations used in the development process; and
    (sa-15_smt.a.4) Documents, manages, and ensures the integrity of changes to the

**Guidance:** Development tools include programming languages and computer-aided design systems. Reviews of development processes include the use of maturity models to determine the potential effectiveness of such processes. Maintaining the integrity of changes to tools and processes facilitates effective supply

**Related:** MA-6, SA-3, SA-4, SA-8, SA-10, SA-11, SR-3, SR-4, SR-5, SR-6, SR-9

**Assessment Objectives:**
- sa-15_obj.a
- sa-15_obj.b

---

## SA-16: Developer-provided Training
Require the developer of the system, system component, or system service to provide the following training on the correct use and operation of the implemented security and privacy functions, controls, and/or mechanisms: {{ insert: param, sa-16_odp }}.

**Guidance:** Developer-provided training applies to external and internal (in-house) developers. Training personnel is essential to ensuring the effectiveness of the controls implemented within organizational systems. Types of training include web-based and computer-based training, classroom-style training, and

**Related:** AT-2, AT-3, PE-3, SA-4, SA-5

---

## SA-17: Developer Security and Privacy Architecture and Design
Require the developer of the system, system component, or system service to produce a design specification and security and privacy architecture that:
  (sa-17_smt.a) Is consistent with the organization’s security and privacy architecture that is an integral part the organization’s enterprise architecture;
  (sa-17_smt.b) Accurately and completely describes the required security and privacy functionality, and the allocation of controls among physical and logical components; and
  (sa-17_smt.c) E

**Guidance:** Developer security and privacy architecture and design are directed at external developers, although they could also be applied to internal (in-house) development. In contrast, [PL-8](#pl-8) is directed at internal developers to ensure that organizations develop a security and privacy architecture t

**Related:** PL-2, PL-8, PM-7, SA-3, SA-4, SA-8, SC-7

**Assessment Objectives:**
- sa-17_obj.a
- sa-17_obj.b
- sa-17_obj.c

---

## SA-20: Customized Development of Critical Components
Reimplement or custom develop the following critical system components: {{ insert: param, sa-20_odp }}.

**Guidance:** Organizations determine that certain system components likely cannot be trusted due to specific threats to and vulnerabilities in those components for which there are no viable security controls to adequately mitigate risk. Reimplementation or custom development of such components may satisfy requir

**Related:** CP-2, RA-9, SA-8

---

## SA-21: Developer Screening
Require that the developer of {{ insert: param, sa-21_odp.01 }}:
  (sa-21_smt.a) Has appropriate access authorizations as determined by assigned {{ insert: param, sa-21_odp.02 }} ; and
  (sa-21_smt.b) Satisfies the following additional personnel screening criteria: {{ insert: param, sa-21_odp.03 }}.

**Guidance:** Developer screening is directed at external developers. Internal developer screening is addressed by [PS-3](#ps-3) . Because the system, system component, or system service may be used in critical activities essential to the national or economic security interests of the United States, organizations

**Related:** PS-2, PS-3, PS-6, PS-7, SA-4, SR-6

**Assessment Objectives:**
- sa-21_obj.a the developer of {{ insert: param, sa-21_odp.01 }} is required to have appropriate access authorizations as determined by assigned {{ insert: param, sa-21_odp.02 }};
- sa-21_obj.b the developer of {{ insert: param, sa-21_odp.01 }} is required to satisfy {{ insert: param, sa-21_odp.03 }}.

---

## SA-22: Unsupported System Components
(sa-22_smt.a) Replace system components when support for the components is no longer available from the developer, vendor, or manufacturer; or
  (sa-22_smt.b) Provide the following options for alternative sources for continued support for unsupported components {{ insert: param, sa-22_odp.01 }}.

**Guidance:** Support for system components includes software patches, firmware updates, replacement parts, and maintenance contracts. An example of unsupported components includes when vendors no longer provide critical software patches or product updates, which can result in an opportunity for adversaries to ex

**Related:** PL-2, SA-3

**Assessment Objectives:**
- sa-22_obj.a system components are replaced when support for the components is no longer available from the developer, vendor, or manufacturer;
- sa-22_obj.b {{ insert: param, sa-22_odp.01 }} provide options for alternative sources for continued support for unsupported components.

---

## SA-23: Specialization
Employ {{ insert: param, sa-23_odp.01 }} on {{ insert: param, sa-23_odp.02 }} supporting mission essential services or functions to increase the trustworthiness in those systems or components.

**Guidance:** It is often necessary for a system or system component that supports mission-essential services or functions to be enhanced to maximize the trustworthiness of the resource. Sometimes this enhancement is done at the design level. In other instances, it is done post-design, either through modification

**Related:** RA-9, SA-8

---

## SA-24: Design For Cyber Resiliency
(sa-24_smt.a) Design organizational systems, system components, or system services to achieve cyber resiliency by:
    (sa-24_smt.a.1) Defining the following cyber resiliency goals: {{ insert: param, sa-24_odp.01 }}.
    (sa-24_smt.a.2) Defining the following cyber resiliency objectives: {{ insert: param, sa-24_odp.02 }}.
    (sa-24_smt.a.3) Defining the following cyber resiliency techniques: {{ insert: param, sa-24_odp.03 }}.
    (sa-24_smt.a.4) Defining the following cyber resiliency implement

**Guidance:** Cyber resiliency is critical to ensuring the survivability of mission critical systems and high value assets. Cyber resiliency focuses on limiting the damage from adversity or the conditions that can cause a loss of assets. Damage can affect: (1) organizations (e.g., loss of reputation, increased ex

**Related:** CA-7, CP-2, CP-4, CP-9, CP-10, CP-11, CP-12, CP-13, IA-10, IR-4, IR-5, PE-11, PE-17, PL-8, PM-7, PM-16, PM-30, PM-31, RA-3, RA-5, RA-9, RA-10, SA-3, SA-8, SA-9, SA-17, SC-3, SC-5, SC-7, SC-10, SC-11, SC-29, SC-30, SC-34, SC-35, SC-36, SC-37, SC-39, SC-44, SC-47, SC-48, SC-49, SC-50, SC-51, SI-3, SI-4, SI-6, SI-7, SI-10, SI-14, SI-15, SI-16, SI-19, SI-20, SI-21, SI-22, SI-23, SR-3, SR-4, SR-5, SR-6, SR-7, SR-9, SR-10, SR-11

**Assessment Objectives:**
- sa-24_obj.a
- sa-24_obj.b
