# NIST 800-53: MP — Media Protection

## MP-1: Policy and Procedures
(mp-1_smt.a) Develop, document, and disseminate to {{ insert: param, mp-1_prm_1 }}:
    (mp-1_smt.a.1) {{ insert: param, mp-01_odp.03 }} media protection policy that:
      (mp-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (mp-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (mp-1_smt.a.2) Procedures

**Guidance:** Media protection policy and procedures address the controls in the MP family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance.

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- mp-1_obj.a
- mp-1_obj.b the {{ insert: param, mp-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the media protection policy and procedures.
- mp-1_obj.c

---

## MP-2: Media Access
Restrict access to {{ insert: param, mp-2_prm_1 }} to {{ insert: param, mp-2_prm_2 }}.

**Guidance:** System media includes digital and non-digital media. Digital media includes flash drives, diskettes, magnetic tapes, external or removable hard disk drives (e.g., solid state, magnetic), compact discs, and digital versatile discs. Non-digital media includes paper and microfilm. Denying access to pat

**Related:** AC-19, AU-9, CP-2, CP-9, CP-10, MA-5, MP-4, MP-6, PE-2, PE-3, SC-12, SC-13, SC-34, SI-12

**Assessment Objectives:**
- mp-2_obj-1 access to {{ insert: param, mp-02_odp.01 }} is restricted to {{ insert: param, mp-02_odp.02 }};
- mp-2_obj-2 access to {{ insert: param, mp-02_odp.03 }} is restricted to {{ insert: param, mp-02_odp.04 }}.

---

## MP-3: Media Marking
(mp-3_smt.a) Mark system media indicating the distribution limitations, handling caveats, and applicable security markings (if any) of the information; and
  (mp-3_smt.b) Exempt {{ insert: param, mp-03_odp.01 }} from marking if the media remain within {{ insert: param, mp-03_odp.02 }}.

**Guidance:** Security marking refers to the application or use of human-readable security attributes. Digital media includes diskettes, magnetic tapes, external or removable hard disk drives (e.g., solid state, magnetic), flash drives, compact discs, and digital versatile discs. Non-digital media includes paper

**Related:** AC-16, CP-9, MP-5, PE-22, SI-12

**Assessment Objectives:**
- mp-3_obj.a system media is marked to indicate distribution limitations, handling caveats, and applicable security markings (if any) of the information;
- mp-3_obj.b {{ insert: param, mp-03_odp.01 }} remain within {{ insert: param, mp-03_odp.02 }}.

---

## MP-4: Media Storage
(mp-4_smt.a) Physically control and securely store {{ insert: param, mp-4_prm_1 }} within {{ insert: param, mp-4_prm_2 }} ; and
  (mp-4_smt.b) Protect system media types defined in MP-4a until the media are destroyed or sanitized using approved equipment, techniques, and procedures.

**Guidance:** System media includes digital and non-digital media. Digital media includes flash drives, diskettes, magnetic tapes, external or removable hard disk drives (e.g., solid state, magnetic), compact discs, and digital versatile discs. Non-digital media includes paper and microfilm. Physically controllin

**Related:** AC-19, CP-2, CP-6, CP-9, CP-10, MP-2, MP-7, PE-3, PL-2, SC-12, SC-13, SC-28, SC-34, SI-12

**Assessment Objectives:**
- mp-4_obj.a
- mp-4_obj.b system media types (defined in MP-04_ODP[01], MP-04_ODP[02], MP-04_ODP[03], MP-04_ODP[04]) are protected until the media are destroyed or sanitized using approved equipment, techniques, and procedures.

---

## MP-5: Media Transport
(mp-5_smt.a) Protect and control {{ insert: param, mp-05_odp.01 }} during transport outside of controlled areas using {{ insert: param, mp-5_prm_2 }};
  (mp-5_smt.b) Maintain accountability for system media during transport outside of controlled areas;
  (mp-5_smt.c) Document activities associated with the transport of system media; and
  (mp-5_smt.d) Restrict the activities associated with the transport of system media to authorized personnel.

**Guidance:** System media includes digital and non-digital media. Digital media includes flash drives, diskettes, magnetic tapes, external or removable hard disk drives (e.g., solid state and magnetic), compact discs, and digital versatile discs. Non-digital media includes microfilm and paper. Controlled areas a

**Related:** AC-7, AC-19, CP-2, CP-9, MP-3, MP-4, PE-16, PL-2, SC-12, SC-13, SC-28, SC-34

**Assessment Objectives:**
- mp-5_obj.a
- mp-5_obj.b accountability for system media is maintained during transport outside of controlled areas;
- mp-5_obj.c activities associated with the transport of system media are documented;
- mp-5_obj.d

---

## MP-6: Media Sanitization
(mp-6_smt.a) Sanitize {{ insert: param, mp-6_prm_1 }} prior to disposal, release out of organizational control, or release for reuse using {{ insert: param, mp-6_prm_2 }} ; and
  (mp-6_smt.b) Employ sanitization mechanisms with the strength and integrity commensurate with the security category or classification of the information.

**Guidance:** Media sanitization applies to all digital and non-digital system media subject to disposal or reuse, whether or not the media is considered removable. Examples include digital media in scanners, copiers, printers, notebook computers, workstations, network components, mobile devices, and non-digital

**Related:** AC-3, AC-7, AU-11, MA-2, MA-3, MA-4, MA-5, PM-22, SI-12, SI-18, SI-19, SR-11

**Assessment Objectives:**
- mp-6_obj.a
- mp-6_obj.b sanitization mechanisms with strength and integrity commensurate with the security category or classification of the information are employed.

---

## MP-7: Media Use
(mp-7_smt.a) {{ insert: param, mp-07_odp.02 }} the use of {{ insert: param, mp-07_odp.01 }} on {{ insert: param, mp-07_odp.03 }} using {{ insert: param, mp-07_odp.04 }} ; and
  (mp-7_smt.b) Prohibit the use of portable storage devices in organizational systems when such devices have no identifiable owner.

**Guidance:** System media includes both digital and non-digital media. Digital media includes diskettes, magnetic tapes, flash drives, compact discs, digital versatile discs, and removable hard disk drives. Non-digital media includes paper and microfilm. Media use protections also apply to mobile devices with in

**Related:** AC-19, AC-20, PL-4, PM-12, SC-34, SC-41

**Assessment Objectives:**
- mp-7_obj.a the use of {{ insert: param, mp-07_odp.01 }} is {{ insert: param, mp-07_odp.02 }} on {{ insert: param, mp-07_odp.03 }} using {{ insert: param, mp-07_odp.04 }};
- mp-7_obj.b the use of portable storage devices in organizational systems is prohibited when such devices have no identifiable owner.

---

## MP-8: Media Downgrading
(mp-8_smt.a) Establish {{ insert: param, mp-08_odp.01 }} that includes employing downgrading mechanisms with strength and integrity commensurate with the security category or classification of the information;
  (mp-8_smt.b) Verify that the system media downgrading process is commensurate with the security category and/or classification level of the information to be removed and the access authorizations of the potential recipients of the downgraded information;
  (mp-8_smt.c) Identify {{ insert

**Guidance:** Media downgrading applies to digital and non-digital media subject to release outside of the organization, whether the media is considered removable or not. When applied to system media, the downgrading process removes information from the media, typically by security category or classification leve

**Assessment Objectives:**
- mp-8_obj.a
- mp-8_obj.b
- mp-8_obj.c {{ insert: param, mp-08_odp.02 }} is identified;
- mp-8_obj.d the identified system media is downgraded using the {{ insert: param, mp-08_odp.01 }}.
