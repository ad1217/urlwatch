import email.utils

from lxml import etree
from lxml.builder import E

import urlwatch
from .handler import JobState


def get_job_history(job, cache_storage, max_history):
    history_data = cache_storage.get_history_data(job.get_guid(), max_history)
    history_data = sorted(history_data.items(), key=lambda kv: kv[1])

    if len(history_data) and getattr(job, 'treat_new_as_changed', False):
        # Insert empty history entry, so first snapshot is diffed against the empty string
        _, first_timestamp = history_data[0]
        history_data.insert(0, ('', first_timestamp))

    for i in range(len(history_data) - 1):
        with JobState(cache_storage, job) as job_state:
            job_state.old_data, job_state.timestamp = history_data[i]
            job_state.new_data, job_state.current_timestamp = history_data[i + 1]

            yield job_state


class RSSGenerator():
    def __init__(self, cache_storage, max_history):
        self.cache_storage = cache_storage
        self.max_history = max_history

    def _rss_metadata(self, feed_metadata):
        """Create XML elements for RSS feed metadata."""
        metadata = {
            "title": "urlwatch Updates",
            "link": urlwatch.__url__,
            "description": urlwatch.__doc__,
            **feed_metadata
        }

        for prop, value in metadata.items():
            el = etree.Element(prop)
            el.text = value
            yield el

    def _rss_item_from_jobstate(self, job_state):
        diff = job_state.get_diff()
        html_diff = etree.tostring(E.pre(diff))

        return E.item(
            E.title(job_state.job.pretty_name()),
            E.description(etree.CDATA(html_diff)),
            E.link(job_state.job.get_location()) if job_state.job.location_is_url() else None,
            E.guid({'isPermaLink': "false"},
                   job_state.job.get_guid() + '.' + str(job_state.current_timestamp)),
            E.pubDate(email.utils.formatdate(job_state.current_timestamp, usegmt=True)))

    def _get_diff_items(self, jobs):
        """For each job: get the history, diff it, and return a RSS item."""
        for job in jobs:
            history = get_job_history(job, self.cache_storage, self.max_history)
            for history_state in history:
                yield self._rss_item_from_jobstate(history_state)

    def generate_feed(self, jobs, feed_metadata, output_file):
        with open(output_file, "wb") as f:
            tree = etree.ElementTree(
                E.rss({'version': '2.0'},
                      E.channel(
                          *self._rss_metadata(feed_metadata),
                          E.generator('urlwatch ' + urlwatch.__version__),
                          *self._get_diff_items(jobs))))
            tree.write(f, pretty_print=True)
