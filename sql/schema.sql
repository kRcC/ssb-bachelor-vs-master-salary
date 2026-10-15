CREATE DATABASE IF NOT EXISTS ssb_case CHARACTER SET utf8mb4;
USE ssb_case;

CREATE TABLE IF NOT EXISTS education_salaries (
    year SMALLINT UNSIGNED NOT NULL,
    field_code CHAR(3) NOT NULL,
    field_name VARCHAR(200) NOT NULL,
    education_level CHAR(1) NOT NULL,
    mean_salary DECIMAL(12,2) NULL,
    median_salary DECIMAL(12,2) NULL,
    jobs INT UNSIGNED NULL,
    PRIMARY KEY (year, field_code, education_level),
    CHECK (education_level IN ('3', '4')),
    CHECK (mean_salary IS NULL OR mean_salary > 0),
    CHECK (median_salary IS NULL OR median_salary > 0)
) ENGINE=InnoDB;
