def _run_job(job, text, saved_paths, tmpdir):
    global CURRENT_JOB
    CURRENT_JOB = job
    try:
        agent = get_agent()

        def on_tool(description):
            if not job["cancelled"]:
                job["events"].append({"type": "activity", "text": description})

        def on_images(payload):
            if not job["cancelled"]:
                job["events"].append({"type": "images", "payload": payload})

        reply = agent.send(text, attachments=saved_paths or None)
        if not job["cancelled"]:
            job["events"].append({"type": "reply", "text": reply or ""})
    except Exception as e:
        print("[B.E.T.A.] job failed:", repr(e))
        if not job["cancelled"]:
            job["events"].append({"type": "error", "text": _friendly_error(e)})
    finally:
        job["done"] = True
        CURRENT_JOB = None
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
