package com.lter.infra.repository;

import com.lter.infra.domain.entity.Script;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ScriptRepository extends JpaRepository<Script, Long> {

    List<Script> findByScriptType(Script.ScriptType scriptType);
}
