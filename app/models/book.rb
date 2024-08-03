class Book < ApplicationRecord
  belongs_to :author
  belongs_to :publisher
  has_many :genres_to_books
  has_many :genres, through: :genres_to_books

  accepts_nested_attributes_for :genres

  validates :title, presence: true, uniqueness: true
  validates :author_id, presence: true
  validates :publisher_id, presence: true
  validates :published_year, presence: true
  validates :page_count, presence: true, numericality: { only_integer: true, greater_than: 0 }

  def self.search(search)
    if search
      where('title LIKE ?', "%#{search}%")
    else
      all
    end
  end
end
