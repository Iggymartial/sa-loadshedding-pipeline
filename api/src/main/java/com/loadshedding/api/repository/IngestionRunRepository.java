package com.loadshedding.api.repository;

import com.loadshedding.api.entity.IngestionRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface IngestionRunRepository extends JpaRepository<IngestionRun, Integer> {

    List<IngestionRun> findTop50ByOrderByRunAtDesc();
}
