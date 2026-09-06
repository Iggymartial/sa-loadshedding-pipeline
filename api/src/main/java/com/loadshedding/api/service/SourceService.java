package com.loadshedding.api.service;

import com.loadshedding.api.dto.SourceResponse;
import com.loadshedding.api.repository.SourceRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SourceService {

    private final SourceRepository sourceRepository;

    public SourceService(SourceRepository sourceRepository) {
        this.sourceRepository = sourceRepository;
    }

    public List<SourceResponse> getAllSources() {
        return sourceRepository.findAll().stream()
                .map(s -> new SourceResponse(s.getId(), s.getCode(), s.getDisplayName()))
                .toList();
    }
}
