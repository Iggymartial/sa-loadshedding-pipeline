package com.loadshedding.api.entity;

import jakarta.persistence.*;

/**
 * Maps to the `sources` table (see db/schema.sql). This lookup table is
 * populated by the Python loader, never by this application - hence no
 * setters and a protected no-arg constructor (required by JPA, but not
 * meant to be used directly).
 */
@Entity
@Table(name = "sources")
public class Source {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Source() {
        // required by JPA/Hibernate
    }

    public Integer getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getDisplayName() {
        return displayName;
    }
}
