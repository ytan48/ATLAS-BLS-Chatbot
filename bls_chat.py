#!/usr/bin/env python3
"""Interactive BLS chatbot using the same ATLAS client as Flask."""

from dotenv import load_dotenv

from atlas_chat import AtlasConfigurationError, AtlasSettings, ask_atlas


def main() -> None:
    load_dotenv()
    try:
        settings = AtlasSettings.from_env()
        settings.validate(require_api_key=True)
    except AtlasConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return

    print(
        "BLS Virtual Advisor"
        f"  |  model: {settings.model}"
        f"  |  effort: {settings.reasoning_effort}"
    )
    print("Type 'quit' or 'exit' to stop.\n")
    last_response = ""

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in {"quit", "exit"}:
            print("Goodbye!")
            break

        try:
            last_response = ask_atlas(
                query,
                last_response=last_response,
                settings=settings,
            )
        except Exception as exc:
            print(f"\nError: {exc}\n")
            continue
        print(f"\nAdvisor:\n{last_response}\n")


if __name__ == "__main__":
    main()
