package com.loadshedding.api.dto;

/**
 * API-facing shape of a source. A Java record is used deliberately here:
 * it's an immutable data carrier with no behaviour, which is exactly
 * what a response DTO should be - Jackson serialises records to JSON
 * automatically, no extra configuration needed.
 */
public record SourceResponse(
        Integer id,
        String code,
        String displayName
) {}
