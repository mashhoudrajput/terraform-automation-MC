-- ============================================================================
-- ClusterDB.sql - Main Hospital Database Schema
-- ============================================================================
-- This file contains the table definitions for the main hospital database.
-- Execute this SQL file after database creation to set up the schema.
-- ============================================================================

-- Set default charset and collation
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ============================================================================
-- PATIENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS patients (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Unique patient identifier',
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    gender ENUM('Male', 'Female', 'Other') DEFAULT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_patient_id (patient_id),
    INDEX idx_name (last_name, first_name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DOCTORS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS doctors (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    doctor_id VARCHAR(50) UNIQUE NOT NULL COMMENT 'Unique doctor identifier',
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    specialization VARCHAR(100),
    license_number VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doctor_id (doctor_id),
    INDEX idx_name (last_name, first_name),
    INDEX idx_specialization (specialization)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- APPOINTMENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS appointments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    appointment_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,
    appointment_date DATETIME NOT NULL,
    status ENUM('Scheduled', 'Completed', 'Cancelled', 'No-Show') DEFAULT 'Scheduled',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    INDEX idx_appointment_id (appointment_id),
    INDEX idx_patient_id (patient_id),
    INDEX idx_doctor_id (doctor_id),
    INDEX idx_appointment_date (appointment_date),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- MEDICAL RECORDS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS medical_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    record_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,
    appointment_id BIGINT,
    diagnosis TEXT,
    treatment TEXT,
    prescription TEXT,
    visit_date DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
    INDEX idx_record_id (record_id),
    INDEX idx_patient_id (patient_id),
    INDEX idx_doctor_id (doctor_id),
    INDEX idx_visit_date (visit_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DEPARTMENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS departments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    department_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    head_doctor_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (head_doctor_id) REFERENCES doctors(id) ON DELETE SET NULL,
    INDEX idx_department_id (department_id),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DOCTOR_DEPARTMENTS (Many-to-Many Relationship)
-- ============================================================================
CREATE TABLE IF NOT EXISTS doctor_departments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    doctor_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    role VARCHAR(50) DEFAULT 'Member',
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    UNIQUE KEY unique_doctor_department (doctor_id, department_id),
    INDEX idx_doctor_id (doctor_id),
    INDEX idx_department_id (department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- MEDICATIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS medications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    medication_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    generic_name VARCHAR(200),
    dosage VARCHAR(50),
    unit VARCHAR(20),
    manufacturer VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_medication_id (medication_id),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- PRESCRIPTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS prescriptions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    prescription_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,
    medical_record_id BIGINT,
    medication_id BIGINT NOT NULL,
    dosage VARCHAR(100),
    frequency VARCHAR(50),
    duration VARCHAR(50),
    instructions TEXT,
    prescribed_date DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE,
    INDEX idx_prescription_id (prescription_id),
    INDEX idx_patient_id (patient_id),
    INDEX idx_doctor_id (doctor_id),
    INDEX idx_prescribed_date (prescribed_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- LABORATORY TESTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS laboratory_tests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(50) UNIQUE NOT NULL,
    test_name VARCHAR(200) NOT NULL,
    test_type VARCHAR(100),
    description TEXT,
    normal_range VARCHAR(100),
    unit VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_test_id (test_id),
    INDEX idx_test_name (test_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- LAB RESULTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS lab_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    result_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id BIGINT NOT NULL,
    test_id BIGINT NOT NULL,
    medical_record_id BIGINT,
    result_value VARCHAR(200),
    result_status ENUM('Normal', 'Abnormal', 'Critical') DEFAULT 'Normal',
    test_date DATETIME NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (test_id) REFERENCES laboratory_tests(id) ON DELETE CASCADE,
    FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    INDEX idx_result_id (result_id),
    INDEX idx_patient_id (patient_id),
    INDEX idx_test_id (test_id),
    INDEX idx_test_date (test_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- BILLING TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS billing (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    bill_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id BIGINT NOT NULL,
    appointment_id BIGINT,
    medical_record_id BIGINT,
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    paid_amount DECIMAL(10, 2) DEFAULT 0.00,
    status ENUM('Pending', 'Paid', 'Partial', 'Cancelled') DEFAULT 'Pending',
    bill_date DATETIME NOT NULL,
    due_date DATE,
    payment_date DATETIME,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
    FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    INDEX idx_bill_id (bill_id),
    INDEX idx_patient_id (patient_id),
    INDEX idx_status (status),
    INDEX idx_bill_date (bill_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

