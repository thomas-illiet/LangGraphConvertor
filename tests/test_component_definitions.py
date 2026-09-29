"""Test the packaged component DSL registry and generation contracts."""

from __future__ import annotations

import importlib.resources

from langflow_converter_mcp.component_definitions import FieldType, get_registry


def test_registry_contains_twenty_valid_unique_definitions() -> None:
    """Startup validation exposes exactly the complete V1 component surface."""
    registry = get_registry()
    index = registry.index()

    assert len(index) == 20
    assert len({item["type"] for item in index}) == 20
    assert all(len(str(item["sha256"])) == 64 for item in index)


def test_every_definition_has_generation_and_test_contracts() -> None:
    """Each component provides ports, recipe guidance, invariants, and tests."""
    registry = get_registry()

    for item in registry.index():
        definition = registry.resolve(str(item["type"]))
        assert definition is not None
        assert definition.recipe.construction
        assert definition.recipe.invocation
        assert definition.recipe.error_handling
        assert definition.invariants
        assert definition.tests
        assert definition.inputs or definition.outputs
        for field in definition.config:
            if field.type is FieldType.SECRET:
                assert field.environment


def test_component_config_schema_is_closed_and_typed() -> None:
    """Generated config schemas forbid extensions and retain field constraints."""
    schema = get_registry().config_schema("OpenAIModel")

    assert schema is not None
    assert schema["additionalProperties"] is False
    assert schema["properties"]["temperature"]["maximum"] == 2.0
    assert schema["properties"]["api_key"]["type"] == "string"


def test_yaml_definitions_are_package_resources() -> None:
    """All YAML contracts are discoverable through importlib.resources for wheels."""
    root = importlib.resources.files("langflow_converter_mcp.components.definitions")
    names = {item.name for item in root.iterdir() if item.name.endswith(".yaml")}

    assert len(names) == 20
    assert {"chat_input.yaml", "chroma.yaml", "condition.yaml"} <= names
