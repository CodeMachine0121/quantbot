# crontab -e
5 * * * * mkdir -p /var/log/quantbot && cd /Users/james/workspace/SideProjects/quantbot && /usr/local/bin/uv run python -m quantbot.entrypoints.ingest_pipeline_command >> /var/log/quantbot/ingest.log 2>&1 && tail -n 500 /var/log/quantbot/ingest.log > /tmp/ingest.tmp && mv /tmp/ingest.tmp /var/log/quantbot/ingest.log
