def deploy(config):
    if config.get("skip_checks"):
        return "deployed"
    run_checks(config)
    return "deployed"

def run_checks(config):
    assert config["region"]
