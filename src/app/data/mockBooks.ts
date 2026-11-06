import { Book } from '../types';

export const mockBooks: Book[] = [
  {
    id: '1',
    title: 'To Kill a Mockingbird',
    author: 'Harper Lee',
    category: 'fiction',
    ageRange: '14+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=400',
    images: [
      'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=400',
      'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400',
      'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=400'
    ],
    description: 'A gripping tale of racial injustice and childhood innocence.',
    isbn: '978-0061120084',
    publishedYear: 1960
  },
  {
    id: '2',
    title: '1984',
    author: 'George Orwell',
    category: 'fiction',
    ageRange: '16+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=400',
    images: [
      'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=400',
      'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?w=400',
      'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=400'
    ],
    description: 'A dystopian social science fiction novel and cautionary tale.',
    isbn: '978-0452284234',
    publishedYear: 1949
  },
  {
    id: '3',
    title: 'The Great Gatsby',
    author: 'F. Scott Fitzgerald',
    category: 'fiction',
    ageRange: '14+',
    status: 'available-soon',
    coverImage: 'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400',
    images: [
      'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400',
      'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=400',
      'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400'
    ],
    description: 'A portrait of the Jazz Age in all its decadence and excess.',
    isbn: '978-0743273565',
    publishedYear: 1925
  },
  {
    id: '4',
    title: 'Pride and Prejudice',
    author: 'Jane Austen',
    category: 'fiction',
    ageRange: '12+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=400',
    images: [
      'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=400',
      'https://images.unsplash.com/photo-1526243741027-444d633d7365?w=400',
      'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400'
    ],
    description: 'A romantic novel of manners set in Georgian England.',
    isbn: '978-0141439518',
    publishedYear: 1813
  },
  {
    id: '5',
    title: 'The Catcher in the Rye',
    author: 'J.D. Salinger',
    category: 'fiction',
    ageRange: '14+',
    status: 'not-available',
    coverImage: 'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?w=400',
    images: [
      'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?w=400',
      'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=400',
      'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400'
    ],
    description: 'The experiences of a teenager in New York City.',
    isbn: '978-0316769174',
    publishedYear: 1951
  },
  {
    id: '6',
    title: 'A Brief History of Time',
    author: 'Stephen Hawking',
    category: 'science',
    ageRange: '16+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400',
    images: [
      'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400',
      'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=400',
      'https://images.unsplash.com/photo-1519682337058-a94d519337bc?w=400'
    ],
    description: 'A landmark volume in science writing.',
    isbn: '978-0553380163',
    publishedYear: 1988
  },
  {
    id: '7',
    title: 'Sapiens',
    author: 'Yuval Noah Harari',
    category: 'history',
    ageRange: '16+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1519682337058-a94d519337bc?w=400',
    images: [
      'https://images.unsplash.com/photo-1519682337058-a94d519337bc?w=400',
      'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400',
      'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400'
    ],
    description: 'A brief history of humankind.',
    isbn: '978-0062316110',
    publishedYear: 2011
  },
  {
    id: '8',
    title: 'The Diary of a Young Girl',
    author: 'Anne Frank',
    category: 'biography',
    ageRange: '12+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400',
    images: [
      'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400',
      'https://images.unsplash.com/photo-1550399105-c4db5fb85c18?w=400',
      'https://images.unsplash.com/photo-1519682337058-a94d519337bc?w=400'
    ],
    description: 'The diary of a Jewish girl hiding during the Holocaust.',
    isbn: '978-0553296983',
    publishedYear: 1947
  },
  {
    id: '9',
    title: 'Harry Potter and the Sorcerer\'s Stone',
    author: 'J.K. Rowling',
    category: 'children',
    ageRange: '8+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1621351183012-e2f9972dd9bf?w=400',
    images: [
      'https://images.unsplash.com/photo-1621351183012-e2f9972dd9bf?w=400',
      'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400',
      'https://images.unsplash.com/photo-1526243741027-444d633d7365?w=400'
    ],
    description: 'A young wizard begins his magical education.',
    isbn: '978-0590353427',
    publishedYear: 1997
  },
  {
    id: '10',
    title: 'The Hunger Games',
    author: 'Suzanne Collins',
    category: 'young-adult',
    ageRange: '12+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=400',
    images: [
      'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=400',
      'https://images.unsplash.com/photo-1490633874781-1c63cc424610?w=400',
      'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?w=400'
    ],
    description: 'A dystopian survival story.',
    isbn: '978-0439023481',
    publishedYear: 2008
  },
  {
    id: '11',
    title: 'Educated',
    author: 'Tara Westover',
    category: 'biography',
    ageRange: '16+',
    status: 'available-soon',
    coverImage: 'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400',
    images: [
      'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400',
      'https://images.unsplash.com/photo-1550399105-c4db5fb85c18?w=400',
      'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400'
    ],
    description: 'A memoir about education and self-invention.',
    isbn: '978-0399590504',
    publishedYear: 2018
  },
  {
    id: '12',
    title: 'The Hobbit',
    author: 'J.R.R. Tolkien',
    category: 'fiction',
    ageRange: '10+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1526243741027-444d633d7365?w=400',
    images: [
      'https://images.unsplash.com/photo-1526243741027-444d633d7365?w=400',
      'https://images.unsplash.com/photo-1621351183012-e2f9972dd9bf?w=400',
      'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=400'
    ],
    description: 'A fantasy adventure of a hobbit.',
    isbn: '978-0547928227',
    publishedYear: 1937
  },
  {
    id: '13',
    title: 'Cosmos',
    author: 'Carl Sagan',
    category: 'science',
    ageRange: '14+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=400',
    images: [
      'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=400',
      'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400',
      'https://images.unsplash.com/photo-1519682337058-a94d519337bc?w=400'
    ],
    description: 'A journey through space and time.',
    isbn: '978-0345539434',
    publishedYear: 1980
  },
  {
    id: '14',
    title: 'The Book Thief',
    author: 'Markus Zusak',
    category: 'young-adult',
    ageRange: '14+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1490633874781-1c63cc424610?w=400',
    images: [
      'https://images.unsplash.com/photo-1490633874781-1c63cc424610?w=400',
      'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=400',
      'https://images.unsplash.com/photo-1621351183012-e2f9972dd9bf?w=400'
    ],
    description: 'A story narrated by Death during WWII.',
    isbn: '978-0375842207',
    publishedYear: 2005
  },
  {
    id: '15',
    title: 'Charlotte\'s Web',
    author: 'E.B. White',
    category: 'children',
    ageRange: '6+',
    status: 'not-available',
    coverImage: 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400',
    images: [
      'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400',
      'https://images.unsplash.com/photo-1621351183012-e2f9972dd9bf?w=400',
      'https://images.unsplash.com/photo-1526243741027-444d633d7365?w=400'
    ],
    description: 'The story of a pig and his spider friend.',
    isbn: '978-0064400558',
    publishedYear: 1952
  },
  {
    id: '16',
    title: 'Becoming',
    author: 'Michelle Obama',
    category: 'biography',
    ageRange: '16+',
    status: 'available',
    coverImage: 'https://images.unsplash.com/photo-1550399105-c4db5fb85c18?w=400',
    images: [
      'https://images.unsplash.com/photo-1550399105-c4db5fb85c18?w=400',
      'https://images.unsplash.com/photo-1589998059171-988d887df646?w=400',
      'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=400'
    ],
    description: 'The memoir of the former First Lady.',
    isbn: '978-1524763138',
    publishedYear: 2018
  }
];
