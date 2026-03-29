#!/usr/bin/env python3
"""Simple CLI chatbot powered by Claude (claude-opus-4-6)."""

import os
import sys
import anthropic


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    conversation = []

    print("Claude Chatbot (type 'quit' or 'exit' to stop, 'clear' to reset)")
    print("-" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "clear":
            conversation.clear()
            print("Conversation cleared.")
            continue

        conversation.append({"role": "user", "content": user_input})

        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system="You are a helpful, friendly assistant.",
                messages=conversation,
            ) as stream:
                print("\nClaude: ", end="", flush=True)
                response_text = ""
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                    response_text += text
                print()

            conversation.append({"role": "assistant", "content": response_text})

        except anthropic.AuthenticationError:
            print("\nError: Invalid API key.")
            sys.exit(1)
        except anthropic.RateLimitError:
            print("\nError: Rate limited. Please wait and try again.")
        except anthropic.APIConnectionError:
            print("\nError: Connection failed. Check your internet connection.")
        except anthropic.APIStatusError as e:
            print(f"\nAPI error ({e.status_code}): {e.message}")


if __name__ == "__main__":
    main()
