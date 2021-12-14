import {browserHistory, withRouter, WithRouterProps} from 'react-router';
import {useTheme} from '@emotion/react';
import {Location} from 'history';
import moment from 'moment';

import ChartZoom from 'sentry/components/charts/chartZoom';
import MarkLine from 'sentry/components/charts/components/markLine';
import ErrorPanel from 'sentry/components/charts/errorPanel';
import LineChart from 'sentry/components/charts/lineChart';
import ReleaseSeries from 'sentry/components/charts/releaseSeries';
import {ChartContainer, HeaderTitleLegend} from 'sentry/components/charts/styles';
import TransitionChart from 'sentry/components/charts/transitionChart';
import TransparentLoadingMask from 'sentry/components/charts/transparentLoadingMask';
import {getSeriesSelection} from 'sentry/components/charts/utils';
import {Panel} from 'sentry/components/panels';
import QuestionTooltip from 'sentry/components/questionTooltip';
import {IconWarning} from 'sentry/icons';
import {t} from 'sentry/locale';
import {Organization} from 'sentry/types';
import {getUtcToLocalDateObject} from 'sentry/utils/dates';
import {axisLabelFormatter, tooltipFormatter} from 'sentry/utils/discover/charts';
import {WebVital} from 'sentry/utils/discover/fields';
import getDynamicText from 'sentry/utils/getDynamicText';
import MetricsRequest from 'sentry/utils/metrics/metricsRequest';
import {decodeScalar} from 'sentry/utils/queryString';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import useApi from 'sentry/utils/useApi';

import {replaceSeriesName, transformEventStatsSmoothed} from '../trends/utils';

import {ViewProps} from './types';
import {getMaxOfSeries, vitalToMetricsField, webVitalMeh, webVitalPoor} from './utils';

type Props = WithRouterProps &
  ViewProps & {
    location: Location;
    orgSlug: Organization['slug'];
    vital: WebVital;
  };

function VitalChart({
  project,
  environment,
  location,
  orgSlug,
  query,
  statsPeriod,
  router,
  start: propsStart,
  end: propsEnd,
  vital,
}: Props) {
  const api = useApi();
  const theme = useTheme();

  const handleLegendSelectChanged = legendChange => {
    const {selected} = legendChange;
    const unselected = Object.keys(selected).filter(key => !selected[key]);

    const to = {
      ...location,
      query: {
        ...location.query,
        unselectedSeries: unselected,
      },
    };
    browserHistory.push(to);
  };

  const start = propsStart ? getUtcToLocalDateObject(propsStart) : null;
  const end = propsEnd ? getUtcToLocalDateObject(propsEnd) : null;
  const utc = decodeScalar(router.location.query.utc) !== 'false';
  const field = `p75(${vitalToMetricsField[vital]})`;

  const legend = {
    right: 10,
    top: 0,
    selected: getSeriesSelection(location),
  };

  const vitalPoor = webVitalPoor[vital];
  const vitalMeh = webVitalMeh[vital];

  const markLines = [
    {
      seriesName: 'Thresholds',
      type: 'line' as const,
      data: [],
      markLine: MarkLine({
        silent: true,
        lineStyle: {
          color: theme.red300,
          type: 'dashed',
          width: 1.5,
        },
        label: {
          show: true,
          position: 'insideEndTop',
          formatter: t('Poor'),
        },
        data: [
          {
            yAxis: vitalPoor,
          } as any, // TODO(ts): date on this type is likely incomplete (needs @types/echarts@4.6.2)
        ],
      }),
    },
    {
      seriesName: 'Thresholds',
      type: 'line' as const,
      data: [],
      markLine: MarkLine({
        silent: true,
        lineStyle: {
          color: theme.yellow300,
          type: 'dashed',
          width: 1.5,
        },
        label: {
          show: true,
          position: 'insideEndTop',
          formatter: t('Meh'),
        },
        data: [
          {
            yAxis: vitalMeh,
          } as any, // TODO(ts): date on this type is likely incomplete (needs @types/echarts@4.6.2)
        ],
      }),
    },
  ];

  const chartOptions = {
    grid: {
      left: '5px',
      right: '10px',
      top: '35px',
      bottom: '0px',
    },
    seriesOptions: {
      showSymbol: false,
    },
    tooltip: {
      trigger: 'axis' as const,
      valueFormatter: (value: number, seriesName?: string) =>
        tooltipFormatter(value, vital === WebVital.CLS ? seriesName : field),
    },
    yAxis: {
      min: 0,
      max: vitalPoor,
      axisLabel: {
        color: theme.chartLabel,
        showMaxLabel: false,
        // coerces the axis to be time based
        formatter: (value: number) => axisLabelFormatter(value, field),
      },
    },
  };

  return (
    <Panel>
      <ChartContainer>
        <HeaderTitleLegend>
          {t('Duration p75')}
          <QuestionTooltip
            size="sm"
            position="top"
            title={t(`The durations shown should fall under the vital threshold.`)}
          />
        </HeaderTitleLegend>
        <ChartZoom router={router} period={statsPeriod} start={start} end={end} utc={utc}>
          {zoomRenderProps => (
            <MetricsRequest
              api={api}
              orgSlug={orgSlug}
              start={start}
              end={end}
              statsPeriod={statsPeriod}
              project={project}
              environment={environment}
              field={[field]}
              query={new MutableSearch(query).formatString()} // TODO(metrics): not all tags will be compatible with metrics
            >
              {({errored, response, loading, reloading}) => {
                if (errored) {
                  return (
                    <ErrorPanel>
                      <IconWarning color="gray500" size="lg" />
                    </ErrorPanel>
                  );
                }

                const data = response?.groups.map(group => ({
                  seriesName: field,
                  data: response.intervals.map((intervalValue, intervalIndex) => ({
                    name: moment(intervalValue).valueOf(),
                    value: group.series[field][intervalIndex],
                  })),
                }));

                const colors =
                  (data && theme.charts.getColorPalette(data.length - 2)) || [];

                const {smoothedResults} = transformEventStatsSmoothed(data);

                const smoothedSeries = smoothedResults
                  ? smoothedResults.map(({seriesName, ...rest}, i: number) => {
                      return {
                        seriesName: replaceSeriesName(seriesName) || 'p75',
                        ...rest,
                        color: colors[i],
                        lineStyle: {
                          opacity: 1,
                          width: 2,
                        },
                      };
                    })
                  : [];

                const seriesMax = getMaxOfSeries(smoothedSeries);
                const yAxisMax = Math.max(seriesMax, vitalPoor);
                chartOptions.yAxis.max = yAxisMax * 1.1;

                return (
                  <ReleaseSeries
                    start={start}
                    end={end}
                    period={statsPeriod}
                    utc={utc}
                    projects={project}
                    environments={environment}
                  >
                    {({releaseSeries}) => (
                      <TransitionChart loading={loading} reloading={reloading}>
                        <TransparentLoadingMask visible={reloading} />
                        {getDynamicText({
                          value: (
                            <LineChart
                              {...zoomRenderProps}
                              {...chartOptions}
                              legend={legend}
                              onLegendSelectChanged={handleLegendSelectChanged}
                              series={[...markLines, ...releaseSeries, ...smoothedSeries]}
                            />
                          ),
                          fixed: 'Web Vitals Chart',
                        })}
                      </TransitionChart>
                    )}
                  </ReleaseSeries>
                );
              }}
            </MetricsRequest>
          )}
        </ChartZoom>
      </ChartContainer>
    </Panel>
  );
}

export default withRouter(VitalChart);