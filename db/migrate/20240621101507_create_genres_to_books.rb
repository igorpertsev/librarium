class CreateGenresToBooks < ActiveRecord::Migration[7.1]
  def change
    create_table :genres_to_books do |t|
      t.integer :genre_id
      t.integer :book_id

      t.timestamps

      t.index [:genre_id, :book_id], unique: true
    end
  end
end
