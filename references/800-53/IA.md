# NIST 800-53: IA — Identification and Authentication

## IA-1: Policy and Procedures
(ia-1_smt.a) Develop, document, and disseminate to {{ insert: param, ia-1_prm_1 }}:
    (ia-1_smt.a.1) {{ insert: param, ia-01_odp.03 }} identification and authentication policy that:
      (ia-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ia-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (ia-1_sm

**Guidance:** Identification and authentication policy and procedures address the controls in the IA family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and pr

**Related:** AC-1, PM-9, PS-8, SI-12

**Assessment Objectives:**
- ia-1_obj.a
- ia-1_obj.b the {{ insert: param, ia-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the identification and authentication policy and procedures;
- ia-1_obj.c

---

## IA-2: Identification and Authentication (Organizational Users)
Uniquely identify and authenticate organizational users and associate that unique identification with processes acting on behalf of those users.

**Guidance:** Organizations can satisfy the identification and authentication requirements by complying with the requirements in [HSPD 12](#f16e438e-7114-4144-bfe2-2dfcad8cb2d0) . Organizational users include employees or individuals who organizations consider to have an equivalent status to employees (e.g., cont

**Related:** AC-2, AC-3, AC-4, AC-14, AC-17, AC-18, AU-1, AU-6, IA-4, IA-5, IA-8, IA-13, MA-4, MA-5, PE-2, PL-4, SA-4, SA-8

**Assessment Objectives:**
- ia-2_obj-1 organizational users are uniquely identified and authenticated;
- ia-2_obj-2 the unique identification of authenticated organizational users is associated with processes acting on behalf of those users.

---

## IA-3: Device Identification and Authentication
Uniquely identify and authenticate {{ insert: param, ia-03_odp.01 }} before establishing a {{ insert: param, ia-03_odp.02 }} connection.

**Guidance:** Devices that require unique device-to-device identification and authentication are defined by type, device, or a combination of type and device. Organization-defined device types include devices that are not owned by the organization. Systems use shared known information (e.g., Media Access Control

**Related:** AC-17, AC-18, AC-19, AU-6, CA-3, CA-9, IA-4, IA-5, IA-9, IA-11, IA-13, SI-4

---

## IA-4: Identifier Management
Manage system identifiers by:
  (ia-4_smt.a) Receiving authorization from {{ insert: param, ia-04_odp.01 }} to assign an individual, group, role, service, or device identifier;
  (ia-4_smt.b) Selecting an identifier that identifies an individual, group, role, service, or device;
  (ia-4_smt.c) Assigning the identifier to the intended individual, group, role, service, or device; and
  (ia-4_smt.d) Preventing reuse of identifiers for {{ insert: param, ia-04_odp.02 }}.

**Guidance:** Common device identifiers include Media Access Control (MAC) addresses, Internet Protocol (IP) addresses, or device-unique token identifiers. The management of individual identifiers is not applicable to shared system accounts. Typically, individual identifiers are the usernames of the system accoun

**Related:** AC-5, IA-2, IA-3, IA-5, IA-8, IA-9, IA-12, MA-4, PE-2, PE-3, PE-4, PL-4, PM-12, PS-3, PS-4, PS-5, SC-37

**Assessment Objectives:**
- ia-4_obj.a system identifiers are managed by receiving authorization from {{ insert: param, ia-04_odp.01 }} to assign to an individual, group, role, or device identifier;
- ia-4_obj.b system identifiers are managed by selecting an identifier that identifies an individual, group, role, service, or device;
- ia-4_obj.c system identifiers are managed by assigning the identifier to the intended individual, group, role, service, or device;
- ia-4_obj.d system identifiers are managed by preventing reuse of identifiers for {{ insert: param, ia-04_odp.02 }}.

---

## IA-5: Authenticator Management
Manage system authenticators by:
  (ia-5_smt.a) Verifying, as part of the initial authenticator distribution, the identity of the individual, group, role, service, or device receiving the authenticator;
  (ia-5_smt.b) Establishing initial authenticator content for any authenticators issued by the organization;
  (ia-5_smt.c) Ensuring that authenticators have sufficient strength of mechanism for their intended use;
  (ia-5_smt.d) Establishing and implementing administrative procedures for initial

**Guidance:** Authenticators include passwords, cryptographic devices, biometrics, certificates, one-time password devices, and ID badges. Device authenticators include certificates and passwords. Initial authenticator content is the actual content of the authenticator (e.g., the initial password). In contrast, t

**Related:** AC-3, AC-6, CM-6, IA-2, IA-4, IA-7, IA-8, IA-9, MA-4, PE-2, PL-4, SC-12, SC-13

**Assessment Objectives:**
- ia-5_obj.a system authenticators are managed through the verification of the identity of the individual, group, role, service, or device receiving the authenticator as part of the initial authenticator distribution;
- ia-5_obj.b system authenticators are managed through the establishment of initial authenticator content for any authenticators issued by the organization;
- ia-5_obj.c system authenticators are managed to ensure that authenticators have sufficient strength of mechanism for their intended use;
- ia-5_obj.d system authenticators are managed through the establishment and implementation of administrative procedures for initial authenticator distribution; lost, compromised, or damaged authenticators; and the revocation of authenticators;
- ia-5_obj.e system authenticators are managed through the change of default authenticators prior to first use;
- ia-5_obj.f system authenticators are managed through the change or refreshment of authenticators {{ insert: param, ia-05_odp.01 }} or when {{ insert: param, ia-05_odp.02 }} occur;
- ia-5_obj.g system authenticators are managed through the protection of authenticator content from unauthorized disclosure and modification;
- ia-5_obj.h
- ia-5_obj.i system authenticators are managed through the change of authenticators for group or role accounts when membership to those accounts changes.

---

## IA-6: Authentication Feedback
Obscure feedback of authentication information during the authentication process to protect the information from possible exploitation and use by unauthorized individuals.

**Guidance:** Authentication feedback from systems does not provide information that would allow unauthorized individuals to compromise authentication mechanisms. For some types of systems, such as desktops or notebooks with relatively large monitors, the threat (referred to as shoulder surfing) may be significan

**Related:** AC-3

---

## IA-7: Cryptographic Module Authentication
Implement mechanisms for authentication to a cryptographic module that meet the requirements of applicable laws, executive orders, directives, policies, regulations, standards, and guidelines for such authentication.

**Guidance:** Authentication mechanisms may be required within a cryptographic module to authenticate an operator accessing the module and to verify that the operator is authorized to assume the requested role and perform services within that role.

**Related:** AC-3, IA-5, SA-4, SC-12, SC-13

---

## IA-8: Identification and Authentication (Non-organizational Users)
Uniquely identify and authenticate non-organizational users or processes acting on behalf of non-organizational users.

**Guidance:** Non-organizational users include system users other than organizational users explicitly covered by [IA-2](#ia-2) . Non-organizational users are uniquely identified and authenticated for accesses other than those explicitly identified and documented in [AC-14](#ac-14) . Identification and authentica

**Related:** AC-2, AC-6, AC-14, AC-17, AC-18, AU-6, IA-2, IA-4, IA-5, IA-10, IA-11, IA-13, MA-4, RA-3, SA-4, SC-8

---

## IA-9: Service Identification and Authentication
Uniquely identify and authenticate {{ insert: param, ia-09_odp }} before establishing communications with devices, users, or other services or applications.

**Guidance:** Services that may require identification and authentication include web applications using digital certificates or services or applications that query a database. Identification and authentication methods for system services and applications include information or code signing, provenance graphs, an

**Related:** IA-3, IA-4, IA-5, IA-13, SC-8

---

## IA-10: Adaptive Authentication
Require individuals accessing the system to employ {{ insert: param, ia-10_odp.01 }} under specific {{ insert: param, ia-10_odp.02 }}.

**Guidance:** Adversaries may compromise individual authentication mechanisms employed by organizations and subsequently attempt to impersonate legitimate users. To address this threat, organizations may employ specific techniques or mechanisms and establish protocols to assess suspicious behavior. Suspicious beh

**Related:** IA-2, IA-8

---

## IA-11: Re-authentication
Require users to re-authenticate when {{ insert: param, ia-11_odp }}.

**Guidance:** In addition to the re-authentication requirements associated with device locks, organizations may require re-authentication of individuals in certain situations, including when roles, authenticators or credentials change, when security categories of systems change, when the execution of privileged f

**Related:** AC-3, AC-11, IA-2, IA-3, IA-4, IA-8

---

## IA-12: Identity Proofing
(ia-12_smt.a) Identity proof users that require accounts for logical access to systems based on appropriate identity assurance level requirements as specified in applicable standards and guidelines;
  (ia-12_smt.b) Resolve user identities to a unique individual; and
  (ia-12_smt.c) Collect, validate, and verify identity evidence.

**Guidance:** Identity proofing is the process of collecting, validating, and verifying a user’s identity information for the purposes of establishing credentials for accessing a system. Identity proofing is intended to mitigate threats to the registration of users and the establishment of their accounts. Standar

**Related:** AC-5, IA-1, IA-2, IA-3, IA-4, IA-5, IA-6, IA-8, IA-13

**Assessment Objectives:**
- ia-12_obj.a users who require accounts for logical access to systems based on appropriate identity assurance level requirements as specified in applicable standards and guidelines are identity proofed;
- ia-12_obj.b user identities are resolved to a unique individual;
- ia-12_obj.c

---

## IA-13: Identity Providers and Authorization Servers
Employ identity providers and authorization servers to manage user, device, and non-person entity (NPE) identities, attributes, and access rights supporting authentication and authorization decisions in accordance with {{ insert: param, ia-13_odp.01 }} using {{ insert: param, ia-13_odp.02 }}.

**Guidance:** Identity providers, both internal and external to the organization, manage the user, device, and NPE authenticators and issue statements, often called identity assertions, attesting to identities of other systems or systems components. Authorization servers create and issue access tokens to identifi

**Related:** AC-3, IA-2, IA-3, IA-8, IA-9, IA-12

**Assessment Objectives:**
- ia-13_obj-1 identity providers are employed to manage user, device, and non-person entity (NPE) identities, attributes and access rights supporting authentication decisions in accordance with {{ insert: param, ia-13_odp.02 }} using {{ insert: param, ia-13_odp.02 }};
- ia-13_obj-2 identity providers are employed to manage user, device, and non-person entity (NPE) identities, attributes and access rights supporting authorization decisions in accordance with {{ insert: param, ia-13_odp.02 }} using {{ insert: param, ia-13_odp.02 }};
- ia-13_obj-3 authorization servers are employed to manage user, device, and non-person entity (NPE) identities, attributes and access rights supporting authentication decisions in accordance with {{ insert: param, ia-13_odp.02 }} using {{ insert: param, ia-13_odp.02 }};
- ia-13_obj-4 authorization servers are employed to manage user, device, and non-person entity (NPE) identities, attributes and access rights supporting authorization decisions in accordance with {{ insert: param, ia-13_odp.02 }} using {{ insert: param, ia-13_odp.02 }};
