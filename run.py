if __name__ == "__main__":
    import sys
    import function.common as common
    import function.static as static
    import dataset_jp
    import dataset_kr

    common.check_directory(static.dir)
    common.check_directory(f"{static.dir}\\log")

    # Usage: python run.py [jp|kr] [--week]
    # - jp  : 일본 데이터 수집
    # - kr  : 한국 데이터 수집 (리팩터링 버전: dataset_kr2)
    # - kr2 : 한국 데이터 수집 (동일하게 dataset_kr2)
    # - kr1 : 구버전 한국 수집 로직 (dataset_kr)
    args = sys.argv[1:]
    target = (args[0].lower() if args else "jp")
    include_week = any(a in ("--week", "week") for a in args[1:])

    if target == "jp":
        dataset_jp.main(include_week=include_week)
    elif target == "kr":
        dataset_kr.main(include_week=include_week)
    else:
        print("Usage: python run.py [jp|kr]")
        sys.exit(1)
