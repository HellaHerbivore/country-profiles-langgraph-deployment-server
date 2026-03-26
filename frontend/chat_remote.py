from api.agent_server import create_thread, search_threads, delete_thread, run_stream_from_message, SSEParser
from uuid import UUID
from colorama import Fore, Style
import nest_asyncio
nest_asyncio.apply()


async def main():
    user_id = UUID("00000000-0000-0000-0000-000000000000")
    try:
        thread_id = await create_thread(user_id)
        print(f"\nCreated thread: {thread_id}")

        threads = await search_threads(user_id)
        print(f"\nFound threads: {threads}")

        configurable = {
            "thread_id": str(thread_id)
        }

        # Create a persistent parser to track seen messages across the conversation
        parser = SSEParser()

        user_input = "Briefly introduce yourself and offer to help me."
        # ...
        while True:
            print(f"\n ---- 🔎 India Researcher ---- \n") # (Optional) Give it a new name tag
            async for result in run_stream_from_message(
                thread_id=thread_id,
                assistant_id="internal_researcher",
                message=user_input,
                configurable=configurable,
                parser=parser
                ):
                print(Fore.CYAN + result + Style.RESET_ALL, end="", flush=True)
        # ...

            user_input = input("\n\nUser ('exit' to quit): ")
            if user_input.lower() in ["exit", "quit"]:
                print("\n\nExit command received. Exiting...\n\n")
                break
            print(f"\n\n ----- 🥷 Human ----- \n\n{user_input}\n")

        # Clean up
        await delete_thread(thread_id)
        print(f"\nDeleted thread: {thread_id}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {str(e)}")
        raise
    
if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
