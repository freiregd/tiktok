import argparse
import json

from .core import Studio


def main():
    parser = argparse.ArgumentParser(description="Fazendeiro Studio local")
    parser.add_argument("command", choices=["serve", "daily", "status"])
    parser.add_argument("--data", default="data")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    studio = Studio(args.data)
    if args.command == "serve":
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port, workers=1)
    elif args.command == "daily":
        for doc in studio.generate():
            print(f"{doc['slot']}. {doc['title']} — {studio.folder(doc)}")
    else:
        print(json.dumps(studio.budget(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
