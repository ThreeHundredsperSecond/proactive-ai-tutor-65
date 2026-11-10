"""Render team-run cards with historical read-only rendering functions."""
import argparse

import health_fipi_extension as health
import fipi_team_run as team


def sample(batch):
    plan = team.read(team.RUN / 'checks/predeclared-controls-v2.json')
    return next(x for x in plan['batches'] if x['batch'] == batch)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=int, required=True)
    args = p.parse_args()
    health.RUN = team.RUN
    health.sample = sample
    health.active = team.active_path
    health.render(args.batch)


if __name__ == '__main__':
    main()
