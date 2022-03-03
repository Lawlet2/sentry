import styled from '@emotion/styled';

import {pinFilter} from 'sentry/actionCreators/pageFilters';
import Button, {ButtonProps} from 'sentry/components/button';
import {IconPin} from 'sentry/icons';
import {t} from 'sentry/locale';
import PageFiltersStore from 'sentry/stores/pageFiltersStore';
import {useLegacyStore} from 'sentry/stores/useLegacyStore';
import {PinnedPageFilter} from 'sentry/types';

type Props = {
  filter: PinnedPageFilter;
  size: Extract<ButtonProps['size'], 'xsmall' | 'zero'>;
  className?: string;
};

function PageFilterPinButton({filter, size, className}: Props) {
  const {pinnedFilters} = useLegacyStore(PageFiltersStore);
  const pinned = pinnedFilters.has(filter);

  const onPin = () => {
    pinFilter(filter, !pinned);
  };

  return (
    <PinButton
      className={className}
      aria-pressed={pinned}
      aria-label={t('Pin')}
      onClick={onPin}
      size={size}
      borderless={size === 'zero'}
      icon={<IconPin size="xs" isSolid={pinned} />}
    />
  );
}

const PinButton = styled(Button)<{size: 'xsmall' | 'zero'}>`
  display: block;
  color: ${p => p.theme.gray300};
  :hover {
    color: ${p => p.theme.subText};
  }
  ${p => p.size === 'zero' && 'background: transparent'};
`;

export default PageFilterPinButton;