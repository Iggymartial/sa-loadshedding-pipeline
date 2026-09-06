package com.loadshedding.api.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Maps to the `ingestion_runs` table (see db/schema.sql) - the audit
 * log of every extract/transform/load attempt, written by the Python
 * pipeline. This is what makes the "did the pipeline actually run
 * last night, and did it work?" question answerable via the API.
 */
@Entity
@Table(name = "ingestion_runs")
public class IngestionRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "run_at", nullable = false)
    private LocalDateTime runAt;

    /**
     * MySQL's ENUM('success','failure') stores lowercase text values.
     * EnumType.STRING compares against the Java enum constant's exact
     * name, so these constants are deliberately lowercase to match the
     * database rather than following the usual UPPER_CASE Java convention.
     */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status;

    @Column(name = "records_fetched", nullable = false)
    private Integer recordsFetched;

    @Column(name = "raw_file")
    private String rawFile;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @Column(columnDefinition = "TEXT")
    private String notes;

    protected IngestionRun() {
        // required by JPA/Hibernate
    }

    public enum Status {
        success, failure
    }

    public Integer getId() {
        return id;
    }

    public LocalDateTime getRunAt() {
        return runAt;
    }

    public Status getStatus() {
        return status;
    }

    public Integer getRecordsFetched() {
        return recordsFetched;
    }

    public String getRawFile() {
        return rawFile;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public String getNotes() {
        return notes;
    }
}
