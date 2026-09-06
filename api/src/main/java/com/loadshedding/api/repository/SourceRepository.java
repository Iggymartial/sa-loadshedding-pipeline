package com.loadshedding.api.repository;

import com.loadshedding.api.entity.Source;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface SourceRepository extends JpaRepository<Source, Integer> {

    Optional<Source> findByCode(String code);
}
