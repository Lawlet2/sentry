from snuba_sdk import Column, Function

from sentry.sentry_metrics.utils import resolve_weak


def init_sessions(metric_ids, alias=None):
    return Function(
        "sumMergeIf",
        [
            Column("value"),
            Function(
                "and",
                [
                    Function(
                        "equals",
                        [
                            Function(
                                "arrayElement",
                                [
                                    Column("tags.value"),
                                    Function(
                                        "indexOf",
                                        [Column("tags.key"), resolve_weak("session.status")],
                                    ),
                                ],
                                "status",
                            ),
                            resolve_weak("init"),
                        ],
                    ),
                    Function("in", [Column("metric_id"), list(metric_ids)]),
                ]
            ),
        ],
        alias,
    )


def crashed_sessions(metric_ids, alias=None):
    return Function(
        "sumMergeIf",
        [
            Column("value"),
            Function(
                "and",
                [
                    Function(
                        "equals",
                        [
                            Function(
                                "arrayElement",
                                [
                                    Column("tags.value"),
                                    Function(
                                        "indexOf",
                                        [Column("tags.key"), resolve_weak("session.status")],
                                    ),
                                ],
                                "status",
                            ),
                            resolve_weak("crashed"),
                        ],
                    ),
                    Function("in", [Column("metric_id"), list(metric_ids)]),
                ]
            ),
        ],
        alias,
    )


def errored_preaggr_sessions(metric_ids, alias=None):
    return Function(
        "sumMergeIf",
        [
            Column("value"),
            Function(
                "and",
                [
                    Function(
                        "equals",
                        [
                            Function(
                                "arrayElement",
                                [
                                    Column("tags.value"),
                                    Function(
                                        "indexOf",
                                        [Column("tags.key"), resolve_weak("session.status")],
                                    ),
                                ],
                                "status",
                            ),
                            resolve_weak("errored_preaggr"),
                        ],
                    ),
                    Function("in", [Column("metric_id"), list(metric_ids)]),
                ],
            ),
        ],
        alias,
    )


def sessions_errored_set(metric_ids, alias=None):
    return Function(
        "uniqCombined64MergeIf",
        [
            Column("value"),
            Function(
                "in",
                [
                    Column("metric_id"),
                    list(metric_ids),
                ],
            ),
        ],
        alias,
    )


def percentage(arg1_snql, arg2_snql, metric_ids, alias=None):
    return Function(
        "multiply",
        [
            100,
            Function("minus", [1, Function("divide", [arg1_snql, arg2_snql])]),
        ],
        alias,
    )
