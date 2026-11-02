import { keys, useT } from '@simple-module-py/i18n';
import { NativeSelect, NativeSelectOption } from '@simple-module-py/ui/components/ui/native-select';
import { LOG_LEVEL_ALL, LOG_LEVELS } from '../logs';

interface Props {
  value: string;
  onChange: (level: string) => void;
}

/** Minimum-level picker shared by the task tab and the search page. */
export function LogLevelSelect({ value, onChange }: Props) {
  const { t } = useT();
  return (
    <NativeSelect
      value={value}
      aria-label={t(keys.background_tasks.logs.level_label)}
      onChange={(e) => onChange(e.target.value)}
    >
      <NativeSelectOption value={LOG_LEVEL_ALL}>
        {t(keys.background_tasks.logs.level_all)}
      </NativeSelectOption>
      {LOG_LEVELS.map((level) => (
        <NativeSelectOption key={level} value={level}>
          {level}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}
