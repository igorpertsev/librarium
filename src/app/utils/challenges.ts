import { useTranslation } from 'react-i18next';
import type { ChallengeDto } from '../../api/types';

/** The challenge's name and description in the interface language (English as the fallback). */
export function useChallengeText() {
  const { i18n } = useTranslation();
  const russian = i18n.language.startsWith('ru');
  return (challenge: Pick<ChallengeDto, 'name_en' | 'name_ru' | 'description_en' | 'description_ru'>) => ({
    name: (russian && challenge.name_ru) || challenge.name_en,
    description: (russian && challenge.description_ru) || challenge.description_en,
  });
}
