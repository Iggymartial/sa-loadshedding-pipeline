package com.loadshedding.api.dto;

import java.time.LocalDateTime;

/**
 * API-facing shape of a stage reading. Deliberately flattens the
 * source's code/name directly onto this record instead of nesting a
 * full SourceResponse object - for this API's actual use cases
 * (dashboards, quick lookups), a flat shape is simpler to consume than
 * a nested one, and it's a decision made explicitly here rather than
 * left to whatever Hibernate's entity graph happens to look like.
 */
public record ReadingResponse(
        Integer id,
        String sourceCode,
        String sourceName,
        Integer stage,
        LocalDateTime stageUpdated,
        LocalDateTime recordedAt
) {}
