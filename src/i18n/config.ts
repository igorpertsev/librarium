import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './en.json';
import ru from './ru.json';

const savedLanguage = localStorage.getItem('language') || 'en';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ru: { translation: ru }
    },
    lng: savedLanguage,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false
    }
  });

// Screen readers pick the pronunciation from <html lang>.
const syncDocumentLanguage = (language: string) => {
  document.documentElement.lang = language;
};
syncDocumentLanguage(i18n.language);
i18n.on('languageChanged', syncDocumentLanguage);

export default i18n;
