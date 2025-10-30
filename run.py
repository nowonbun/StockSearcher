if __name__ == "__main__":
    import sys
    import function.common as common
    import function.static as static
    import dataset_jp
    import dataset_kr

    common.check_directory(static.dir)
    common.check_directory(f"{static.dir}\\log")

    # Usage: python run.py [jp|kr|kr2|kr1]
    # - jp  : 일본 데이터 수집
    # - kr  : 한국 데이터 수집 (리팩터링 버전: dataset_kr2)
    # - kr2 : 한국 데이터 수집 (동일하게 dataset_kr2)
    # - kr1 : 구버전 한국 수집 로직 (dataset_kr)
    args = sys.argv[1:]
    target = (args[0].lower() if args else "jp")

    if target == "jp":
        dataset_jp.main()
    elif target == "kr":
        dataset_kr.main()
    else:
        print("Usage: python run.py [jp|kr]")
        sys.exit(1)
