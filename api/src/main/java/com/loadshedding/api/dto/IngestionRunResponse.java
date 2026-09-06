package com.loadshedding.api.dto;

import java.time.LocalDateTime;

public record IngestionRunResponse(
        Integer id,
        LocalDateTime runAt,
        String status,
        Integer recordsFetched,
        String rawFile,
        String errorMessage,
        String notes
) {}
