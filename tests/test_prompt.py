from pedidos.prompt import build_system_prompt


def test_prompt_lists_the_real_values_from_the_database(sample_db):
    prompt = build_system_prompt(sample_db)
    assert "pais: España, Francia" in prompt
    assert "estado: cancelado, completado" in prompt
    assert "producto: Monitor, Ratón, Tablet, Teclado" in prompt
    assert "fecha: from 2024-03-10 to 2025-04-01" in prompt


def test_a_month_without_a_year_is_resolved_to_its_latest_occurrence(sample_db):
    # The sample has March in 2024 and in 2025: "marzo" alone must mean 2025-03.
    prompt = build_system_prompt(sample_db)
    assert "marzo → 2025-03, abril → 2025-04" in prompt


def test_prompt_never_contains_customer_data(sample_db):
    prompt = build_system_prompt(sample_db)
    for customer in ("Ana Ruiz", "Luis Gil", "Marie Dubois"):
        assert customer not in prompt
